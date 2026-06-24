//! flash_dip_buy — flash-crash dip-buy demo pilot 策略（E1-D 本體）。
//!
//! MODULE_NOTE：
//!   模塊用途：在 UTC 日首 tick 對 26 survivor 大-cap 以 bounded demo near-touch
//!     PostOnly maker limit BUY 取樣 fill/fee/slippage；fill 後持有 N=3 日，於
//!     entry_day+N 的 UTC 日首 tick 平倉（day-clustered，對齊研究面板）。純 demo pilot，flag-OFF +
//!     active=false 雙鎖預設、demo-only kind gate（registry.rs:47 create_for_engine）。
//!   入場條件（ALL true，UTC 日首 tick）：
//!     1. self.active（TOML active=true，且 env flag 已於 factory gate 守住建構）
//!     2. symbol ∈ allowed_symbols（26 survivor universe）
//!     3. 當前 symbol 無本策略持倉（cross-strategy 占用 → skip）
//!     4. 本策略 open + pending working order 並發 < max_concurrent（producer-side
//!        軟層；硬層 = per_strategy.max_concurrent_positions risk config，agent 不可放寬。
//!        硬層真實 enforce 於 intent_processor/router.rs per_strategy_concurrency_rejection
//!        —— 依 owner_strategy 重數 PaperState 真倉，重啟 under-count 後仍 fail-closed）
//!     5. prior_close 可得；或 bounded demo near-touch 模式用 current_price fallback
//!        只作 thesis/logging，不阻斷 fill-discovery。
//!   出場條件：fill 後 entry_day + hold_days 的「UTC 日首 tick」emit Close。
//!   主要類/函數：FlashDipBuy、on_tick（三分支：entry-arm / hold-exit / cross-skip）、
//!     should_emit_close、import_positions / on_fill / on_close_confirmed override、
//!     seed_prior_close（boot seed setter）、entry_ts checkpoint sidecar 讀寫。
//!   依賴：super::{Strategy, StrategyAction}、params::*、intent_processor::OrderIntent、
//!     order_manager::TimeInForce、tick_pipeline::TickContext、openclaw_core::now_ms。
//!   硬邊界：
//!     - cadence 用 wall-clock `openclaw_core::now_ms()`（SystemTime epoch），
//!       **禁** 用 `ctx.timestamp_ms`（= event.ts_ms = WS payload-ts；2026-06-15
//!       Fix-4 教訓：payload-ts 曾污染 cadence）。
//!     - emit 真實 confidence（cost_gate min_confidence 是 live gate）；**禁** 為過
//!       cost_gate 硬設高 confidence（E3 #5）。
//!     - survival floor **不** 在此策略（label-conditional）：真 floor = 通用 P1
//!       per_trade_risk_pct(2%) + position_size_max_pct + limits.max_order_notional_usdt
//!       + 並發硬層 per_strategy.max_concurrent_positions（全 label-independent /
//!       denylisted；enforce 於 router gate，見上條件 4）。本策略只回
//!       Vec<StrategyAction>，持 0 個 OrderManager/REST handle
//!       （Root Principle 1 單一寫入口）。
//!     - entry_ts 跨重啟保真：Bybit demo snapshot 種倉用 updated_time（非 createdTime，
//!       startup/mod.rs:654 親證）+ owner_strategy="bybit_sync"，故 entry_ts 與歸屬
//!       皆於重啟後重置 → N 日 hold clock 不可靠。緩解：本策略 fill 後把真 entry_ts
//!       持久化到 OPENCLAW_DATA_DIR 的 JSON sidecar，import_positions 時還原覆寫，
//!       使 hold clock 跨重啟 + 同向加倉確定性重建（Q2 robust 選項；trading.positions
//!       表不存在故不走 migration）。
//!   research / design ref:
//!     - srv/docs/CCAgentWorkSpace/Operator/2026-06-18--PA--flash-crash-dipbuy-demo-pilot-design.md

use std::collections::{HashMap, HashSet};

use serde::{Deserialize, Serialize};
use tracing::{info, warn};

use super::params::{ParamRange, StrategyParams};
use super::{Strategy, StrategyAction};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};

pub mod params;

#[cfg(test)]
mod tests;

pub use params::FlashDipBuyParams;
use params::{
    compute_bounded_near_touch_limit, compute_dip_level, hold_expired, is_first_tick_of_utc_day,
    DEFAULT_HOLD_DAYS, DEFAULT_K_DIP, DEFAULT_MAX_CONCURRENT, DEFAULT_NEAR_TOUCH_OFFSET_BPS,
    DEFAULT_NOTIONAL_FRAC, MS_PER_UTC_DAY,
};

/// sentinel qty → 即使有固定名目 sizing，仍走 gate stack 的 Kelly/P1 夾擊。
/// 為什麼保留 sentinel 路徑：on_tick 無 equity/balance（TickContext 不含），
/// 策略無法在 emit 時算 fixed_notional_qty；故 emit sentinel 讓 gate 用通用
/// P1(2%)/position_size sizing（保守、label-independent）。fixed_notional_qty 純函式
/// 由 E1-A 提供供 band-external cap 與離線分析使用，非 emit-time sizing。
const FLASH_DIP_SENTINEL_QTY: f64 = 1e9;

/// PostOnly maker offset / buffer（與 funding_* / lcf 範式對齊；但本策略用「靜態
/// 深價」直接 set limit_price，不走 compute_post_only_price at-touch）。
const FLASH_DIP_MAKER_TIMEOUT_FLOOR_MS: u64 = 15_000;

/// entry_ts checkpoint sidecar 檔名（OPENCLAW_DATA_DIR 下，per pilot demo-only）。
const ENTRY_TS_CHECKPOINT_FILE: &str = "flash_dip_buy_entry_ts.json";

// ──────────────────────────────────────────────────────────────────────────
// FlashDipBuy strategy struct
// ──────────────────────────────────────────────────────────────────────────

pub struct FlashDipBuy {
    active: bool,

    /// 靜態深價深度 K。
    pub k_dip: f64,
    /// hold 持有天數 N。
    pub hold_days: u32,
    /// 並發上限 C（producer-side 軟層）。
    pub max_concurrent: u32,
    /// 固定名目佔比 nf（離線分析 / cap 同義；emit 走 sentinel）。
    pub notional_frac: f64,
    /// Demo bounded fill-discovery：true 時以 near-touch PostOnly 替代深價 no-touch。
    pub bounded_demo_near_touch: bool,
    /// near-touch 掛單距當前 last price 的 bps offset。
    pub near_touch_offset_bps: f64,
    /// 26 survivor universe。
    pub allowed_symbols: Vec<String>,

    /// prior_close per symbol：boot 1d REST seed → KlineManager 1d buffer →
    /// seed_prior_close()。leak-free（前一完整 UTC 日收盤，次日使用）。
    prior_close: HashMap<String, f64>,

    /// 上次武裝入場的 UTC 日索引 per symbol（daily cadence；-1 = 從未）。
    last_acted_day: HashMap<String, i64>,

    /// 本策略當前持倉的 symbol 集合（producer-side 並發計數 + cross-strategy 盲區補償）。
    open_symbols: HashSet<String>,

    /// 本策略已發出但未成交/未拒絕的 entry working order 到期時間。
    ///
    /// 為什麼策略內也要記：router hard cap 只看已成交 PaperState positions，
    /// 未成交 PostOnly resting order 不會進 open_symbols；若不記 pending，daily
    /// batch 會在 max_concurrent=3 時同時掛出 26 張 no-fill 單。
    pending_entry_expiry: HashMap<String, u64>,

    /// 本策略自有 entry_ts_ms per symbol（跨重啟保真；持久化到 sidecar）。
    entry_ts: HashMap<String, u64>,

    /// 上次「武裝平倉」的 UTC 日索引 per symbol（day-clustered exit，防同日重發 Close）。
    last_exit_day: HashMap<String, i64>,

    /// CONF-D：confidence 縮放係數（預設 1.0）。
    conf_scale: f64,
}

impl Default for FlashDipBuy {
    fn default() -> Self {
        Self::new()
    }
}

impl FlashDipBuy {
    pub fn new() -> Self {
        Self {
            active: false,
            k_dip: DEFAULT_K_DIP,
            hold_days: DEFAULT_HOLD_DAYS,
            max_concurrent: DEFAULT_MAX_CONCURRENT,
            notional_frac: DEFAULT_NOTIONAL_FRAC,
            bounded_demo_near_touch: true,
            near_touch_offset_bps: DEFAULT_NEAR_TOUCH_OFFSET_BPS,
            allowed_symbols: params::default_allowed_symbols(),
            prior_close: HashMap::new(),
            last_acted_day: HashMap::new(),
            open_symbols: HashSet::new(),
            pending_entry_expiry: HashMap::new(),
            entry_ts: HashMap::new(),
            last_exit_day: HashMap::new(),
            conf_scale: 1.0,
        }
    }

    /// Stage 1 universe fence：symbol 必 ∈ allowed_symbols。
    fn is_allowed_symbol(&self, sym: &str) -> bool {
        self.allowed_symbols.iter().any(|s| s.as_str() == sym)
    }

    /// 計算「距當前 UTC 日終」毫秒，作為 maker_timeout（日終撤未成交掛單）。
    /// 不變量：至少 FLASH_DIP_MAKER_TIMEOUT_FLOOR_MS（避免接近午夜時 timeout≈0
    /// 致掛單立即被 sweep）。
    fn maker_timeout_to_day_end(now_wall_ms: u64) -> u64 {
        let into_day = now_wall_ms % MS_PER_UTC_DAY;
        let to_end = MS_PER_UTC_DAY.saturating_sub(into_day);
        to_end.max(FLASH_DIP_MAKER_TIMEOUT_FLOOR_MS)
    }

    fn prune_expired_pending_entries(&mut self, now_wall_ms: u64) {
        self.pending_entry_expiry
            .retain(|_, expiry_ms| *expiry_ms > now_wall_ms);
    }

    fn producer_active_entry_count(&self) -> usize {
        let mut symbols = self.open_symbols.clone();
        symbols.extend(self.pending_entry_expiry.keys().cloned());
        symbols.len()
    }

    /// OPENCLAW_DATA_DIR/flash_dip_buy_entry_ts.json 路徑。
    fn checkpoint_path() -> std::path::PathBuf {
        let dir =
            std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".to_string());
        std::path::PathBuf::from(dir).join(ENTRY_TS_CHECKPOINT_FILE)
    }

    /// 把 self.entry_ts 原子寫入 sidecar（write-tmp + rename）。
    /// 為什麼 fail-soft：checkpoint 寫失敗不可阻斷交易熱路徑；最壞情況退化為
    /// 「entry_ts 跨重啟用 Bybit updated_time」（保守，hold 可能稍早觸發 ≈ 提前平倉，
    /// 非資本風險，demo-only）。
    fn persist_entry_ts(&self) {
        let path = Self::checkpoint_path();
        let tmp = path.with_extension("json.tmp");
        let json = match serde_json::to_string(&self.entry_ts) {
            Ok(s) => s,
            Err(e) => {
                warn!(error = %e, "flash_dip_buy: entry_ts checkpoint serialize failed");
                return;
            }
        };
        if let Err(e) = std::fs::write(&tmp, &json) {
            warn!(error = %e, path = %tmp.display(), "flash_dip_buy: entry_ts checkpoint write failed");
            return;
        }
        if let Err(e) = std::fs::rename(&tmp, &path) {
            warn!(error = %e, "flash_dip_buy: entry_ts checkpoint rename failed");
        }
    }

    /// 從 sidecar 還原 entry_ts（fail-soft：缺檔/解析失敗 = 空 map，退回 Bybit ts）。
    fn load_entry_ts_checkpoint() -> HashMap<String, u64> {
        let path = Self::checkpoint_path();
        match std::fs::read_to_string(&path) {
            Ok(s) => serde_json::from_str(&s).unwrap_or_default(),
            Err(_) => HashMap::new(),
        }
    }

    /// E2 HIGH fix (2026-06-18)：讀 sidecar 取「本 pilot 上次持有過的 symbol 集合」。
    /// sidecar 的 key 即歸屬證據 —— entry_ts 只在 on_fill / import_positions 對
    /// owner=="flash_dip_buy" 的倉寫入，故 key 集合 == flash_dip 真持倉 symbol。
    /// 為什麼 static / 不經 instance：bootstrap re-claim 必須在策略「註冊之前」
    /// （bootstrap.rs register@:830 晚於 triage@:477）跑，那時尚無 FlashDipBuy
    /// instance，需純靜態讀 sidecar。fail-soft：缺檔/解析失敗 = 空 Vec（不 reclaim，
    /// 退化為舊行為 → triage 仍會把 pilot 倉改標 ma_crossover，但僅 flag-ON 且
    /// 真有 sidecar 殘留時才走到，且不影響其他策略）。
    pub fn sidecar_owned_symbols() -> Vec<String> {
        Self::load_entry_ts_checkpoint().into_keys().collect()
    }

    /// 平倉決策（純判定）：本策略持倉 + entry_day+N 的 UTC 日首 tick →
    /// Some((reason, today_utc_day_index))。回傳 today 供呼叫端 set last_exit_day。
    /// 為什麼 gate 到 UTC 日首 tick：day-clustered exit 對齊研究面板（Q5 預設）。
    /// 不變量：entry_ts 取本策略自有 checkpoint（非 ctx position entry_ts，後者
    /// 跨重啟被 Bybit updated_time 重置）。
    fn should_emit_close(&self, sym: &str, now_wall_ms: u64) -> Option<(&'static str, i64)> {
        let entry_ts = *self.entry_ts.get(sym)?;
        if !hold_expired(now_wall_ms, entry_ts, self.hold_days) {
            return None;
        }
        // day-clustered：只在 UTC 日首 tick emit Close，且當日只發一次
        // （last_exit_day 嚴格小於 today 才觸發）。
        let last_exit = self.last_exit_day.get(sym).copied().unwrap_or(-1);
        let (first_tick, today) = is_first_tick_of_utc_day(now_wall_ms, last_exit);
        if first_tick {
            Some(("flash_dip_hold_3d_expiry", today))
        } else {
            None
        }
    }

    /// IPC `update_strategy_params` 熱更新。
    pub fn update_params(&mut self, params: FlashDipBuyUpdateParams) -> Result<(), String> {
        params.validate()?;
        self.active = params.active;
        self.k_dip = params.k_dip;
        self.hold_days = params.hold_days;
        self.max_concurrent = params.max_concurrent;
        self.notional_frac = params.notional_frac;
        self.bounded_demo_near_touch = params.bounded_demo_near_touch;
        self.near_touch_offset_bps = params.near_touch_offset_bps;
        self.allowed_symbols = params.allowed_symbols.clone();
        info!(
            strategy = "flash_dip_buy",
            active = self.active,
            k_dip = self.k_dip,
            hold_days = self.hold_days,
            max_concurrent = self.max_concurrent,
            bounded_demo_near_touch = self.bounded_demo_near_touch,
            near_touch_offset_bps = self.near_touch_offset_bps,
            "params updated via IPC"
        );
        Ok(())
    }

    /// 當前 tunable 狀態快照成 IPC payload。
    pub fn get_params(&self) -> FlashDipBuyUpdateParams {
        FlashDipBuyUpdateParams {
            active: self.active,
            k_dip: self.k_dip,
            hold_days: self.hold_days,
            max_concurrent: self.max_concurrent,
            notional_frac: self.notional_frac,
            bounded_demo_near_touch: self.bounded_demo_near_touch,
            near_touch_offset_bps: self.near_touch_offset_bps,
            allowed_symbols: self.allowed_symbols.clone(),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// FlashDipBuyUpdateParams (IPC payload)
// ──────────────────────────────────────────────────────────────────────────

/// IPC `update_strategy_params` 的 flash_dip_buy payload schema。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct FlashDipBuyUpdateParams {
    pub active: bool,
    pub k_dip: f64,
    pub hold_days: u32,
    pub max_concurrent: u32,
    pub notional_frac: f64,
    pub bounded_demo_near_touch: bool,
    pub near_touch_offset_bps: f64,
    pub allowed_symbols: Vec<String>,
}

impl Default for FlashDipBuyUpdateParams {
    fn default() -> Self {
        let p = FlashDipBuyParams::default();
        Self {
            active: p.active,
            k_dip: p.k_dip,
            hold_days: p.hold_days,
            max_concurrent: p.max_concurrent,
            notional_frac: p.notional_frac,
            bounded_demo_near_touch: p.bounded_demo_near_touch,
            near_touch_offset_bps: p.near_touch_offset_bps,
            allowed_symbols: p.allowed_symbols,
        }
    }
}

impl StrategyParams for FlashDipBuyUpdateParams {
    fn param_ranges() -> Vec<ParamRange> {
        FlashDipBuyParams::param_ranges()
    }

    fn validate(&self) -> Result<(), String> {
        let mirror = FlashDipBuyParams {
            active: self.active,
            k_dip: self.k_dip,
            hold_days: self.hold_days,
            max_concurrent: self.max_concurrent,
            notional_frac: self.notional_frac,
            bounded_demo_near_touch: self.bounded_demo_near_touch,
            near_touch_offset_bps: self.near_touch_offset_bps,
            allowed_symbols: self.allowed_symbols.clone(),
        };
        mirror.validate()
    }
}

// ──────────────────────────────────────────────────────────────────────────
// Strategy trait impl
// ──────────────────────────────────────────────────────────────────────────

impl Strategy for FlashDipBuy {
    fn name(&self) -> &str {
        "flash_dip_buy"
    }

    fn is_active(&self) -> bool {
        self.active
    }

    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// flash_dip_buy 消費 Tier 1 OHLCV（prior daily close，1d kline-derived）；
    /// 無 Tier 2-4 alpha source。Ta1m 為既有 Tier 1 TA/OHLCV tag。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::Ta1m];
        TAGS
    }

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        if !self.active {
            return vec![];
        }

        let sym = ctx.symbol;
        if !self.is_allowed_symbol(sym) {
            return vec![];
        }

        // ── cadence 時鐘：wall-clock（must-fix #6 / Fix-4）；禁 ctx.timestamp_ms ──
        // ctx.timestamp_ms = event.ts_ms = WS payload-ts，跨 replay / 非單調 / 可被
        // payload 污染；UTC 日判定必須用 openclaw_core::now_ms()（SystemTime epoch）。
        let now_wall_ms = openclaw_core::now_ms();
        self.prune_expired_pending_entries(now_wall_ms);

        let current_price = ctx.price;
        if !current_price.is_finite() || current_price <= 0.0 {
            return vec![];
        }

        // ── 三分支：本策略持倉(exit) / cross-strategy 占用(skip) / 無倉(entry-arm) ──
        let owned_position = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name());

        match owned_position {
            Some(_pos) => {
                // ── Hold-exit 分支：entry_day+N 的 UTC 日首 tick emit Close ──
                if let Some((reason, today)) = self.should_emit_close(sym, now_wall_ms) {
                    self.last_exit_day.insert(sym.to_string(), today);
                    let confidence = (0.8 * self.conf_scale).clamp(0.0, 1.0);
                    info!(
                        strategy = "flash_dip_buy",
                        symbol = sym,
                        reason,
                        "hold expiry Close emitted (day-clustered)"
                    );
                    return vec![StrategyAction::Close {
                        symbol: sym.to_string(),
                        confidence,
                        reason: reason.to_string(),
                    }];
                }
                vec![]
            }
            None if ctx.position_state.is_some() => {
                // cross-strategy 占用同 symbol → skip（避免無限 reject hot loop）。
                vec![]
            }
            None => {
                // ── Entry-arm 分支：UTC 日首 tick 武裝入場 ──
                if !ctx.h0_allowed {
                    return vec![];
                }

                // daily cadence：當日是否首 tick（last_acted_day 嚴格小於 today）。
                let last_acted = self.last_acted_day.get(sym).copied().unwrap_or(-1);
                let (first_tick, today) = is_first_tick_of_utc_day(now_wall_ms, last_acted);
                if !first_tick {
                    return vec![];
                }

                // ── 並發 producer-side 軟層（open positions + pending working orders）──
                // 為什麼要數 pending：PostOnly resting order 未 fill 前不進 PaperState，
                // 若只看 open_symbols，day-first batch 會在 max_concurrent=3 時發出
                // 26 張 pending 單。硬上限仍由風控層守已成交倉位。
                if self.producer_active_entry_count() as u32 >= self.max_concurrent {
                    return vec![];
                }

                // prior_close（boot 1d seed）；static thesis 缺 seed 則 inert。
                // bounded demo near-touch 的實際掛單價只依賴 current_price 和 offset，
                // 因此缺 prior_close 不應再讓 fill-discovery 每日靜默停擺；fallback
                // 僅用於 thesis_limit_price logging / confidence 說明，不放寬風控。
                let (prior_close, prior_close_source) = match self.prior_close.get(sym).copied() {
                    Some(pc) => (pc, "db_1d_seed"),
                    None if self.bounded_demo_near_touch => {
                        (current_price, "bounded_near_touch_current_price_fallback")
                    }
                    None => {
                        // 當日標記已嘗試（避免每 tick 重查），但不入場。
                        self.last_acted_day.insert(sym.to_string(), today);
                        return vec![];
                    }
                };

                // 靜態深價 thesis 仍需可計算；bounded demo 模式只替換「實際掛單價」，
                // 不把缺 prior_close / 壞 K 的信號當成可交易。
                let thesis_limit_price = match compute_dip_level(prior_close, self.k_dip) {
                    Some(p) => p,
                    None => {
                        self.last_acted_day.insert(sym.to_string(), today);
                        return vec![];
                    }
                };
                let (limit_price, limit_mode) = if self.bounded_demo_near_touch {
                    match compute_bounded_near_touch_limit(
                        current_price,
                        self.near_touch_offset_bps,
                    ) {
                        Some(p) => (p, "bounded_demo_near_touch"),
                        None => {
                            self.last_acted_day.insert(sym.to_string(), today);
                            return vec![];
                        }
                    }
                } else {
                    (thesis_limit_price, "static_dip_thesis")
                };

                // 當日武裝完成（無論掛單後是否成交，當日後續 tick 不重複武裝）。
                self.last_acted_day.insert(sym.to_string(), today);

                // ── 誠實 confidence（E3 #5）：基於 dip 深度的真實信心，不硬設高值 ──
                // K=0.15 靜態深價是一個保守的均值回歸 thesis；confidence 反映「研究面板
                // day-clustered 顯著性不強（boot_t≈1.4 含 0）」的誠實不確定性，
                // 不為過 cost_gate 而拉高（cost_gate min_confidence 是 live gate）。
                let confidence = (0.55 * self.conf_scale).clamp(0.0, 1.0);

                let maker_timeout_ms = Self::maker_timeout_to_day_end(now_wall_ms);
                self.pending_entry_expiry.insert(
                    sym.to_string(),
                    now_wall_ms.saturating_add(maker_timeout_ms),
                );

                info!(
                    strategy = "flash_dip_buy",
                    symbol = sym,
                    prior_close,
                    prior_close_source,
                    k_dip = self.k_dip,
                    thesis_limit_price,
                    limit_price,
                    limit_mode,
                    near_touch_offset_bps = self.near_touch_offset_bps,
                    pending_entry_count = self.pending_entry_expiry.len(),
                    confidence,
                    maker_timeout_ms,
                    "dip-buy maker limit armed (UTC day-first tick)"
                );

                vec![StrategyAction::Open(OrderIntent::new_trade(
                    sym.to_string(),
                    true, // dip-buy = long only
                    FLASH_DIP_SENTINEL_QTY,
                    confidence,
                    self.name().to_string(),
                    "limit".to_string(),
                    Some(limit_price),
                    None, // confluence_score
                    None, // persistence_elapsed_ms
                    Some(TimeInForce::PostOnly),
                    Some(maker_timeout_ms),
                ))]
            }
        }
    }

    /// rejection：當日已 set last_acted_day，無 cooldown 額外狀態需回滾。
    /// 為什麼不回滾 last_acted_day：被治理 gate 拒 = 當日不再嘗試（daily cadence
    /// 語意），保守且避免同日重發 hot loop。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        if intent.strategy == self.name() {
            self.pending_entry_expiry.remove(&intent.symbol);
        }
        // last_acted_day 不回滾（daily cadence 已透過 last_acted_day 防同日同 symbol 重發）。
    }

    /// fill confirmed：記錄真 entry_ts（wall-clock）+ 入開倉集 + 持久化 checkpoint。
    /// 為什麼用 wall-clock 而非 fill.ts：hold clock 與 cadence 同源（must-fix #6）；
    /// fill ts 可能是 payload-ts。同向加倉只保留首次 entry_ts（first-write-wins，
    /// 對齊 round-trip 語意 + 防 hold clock 被加倉刷新）。
    fn on_fill(&mut self, intent: &OrderIntent, _fill: &openclaw_core::execution::FillResult) {
        if intent.strategy != self.name() {
            return;
        }
        let sym = &intent.symbol;
        self.pending_entry_expiry.remove(sym);
        let now_wall_ms = openclaw_core::now_ms();
        self.entry_ts.entry(sym.clone()).or_insert(now_wall_ms);
        self.open_symbols.insert(sym.clone());
        self.persist_entry_ts();
    }

    /// bootstrap：從 paper_state 重建本策略 open set + 從 sidecar 還原真 entry_ts。
    /// 為什麼雙源重建：paper_state 給「現在持有哪些倉」（owner_strategy 過濾），
    /// sidecar 給「真 entry_ts」（Bybit updated_time 不可靠）。兩者交集 = 可靠 hold clock。
    fn import_positions(&mut self, paper_state: &crate::paper_state::PaperState) {
        let checkpoint = Self::load_entry_ts_checkpoint();
        let mut imported = 0_usize;
        let mut kept_entry_ts: HashMap<String, u64> = HashMap::new();
        for pos in paper_state.positions() {
            if pos.owner_strategy == self.name() {
                self.open_symbols.insert(pos.symbol.clone());
                self.pending_entry_expiry.remove(&pos.symbol);
                // 優先用 sidecar 真 entry_ts；缺則退回 paper_state（Bybit updated_time，
                // 保守 hold 可能稍早觸發）。
                let entry_ts = checkpoint
                    .get(&pos.symbol)
                    .copied()
                    .unwrap_or(pos.entry_ts_ms);
                kept_entry_ts.insert(pos.symbol.clone(), entry_ts);
                imported += 1;
            }
        }
        self.entry_ts = kept_entry_ts;
        if imported > 0 {
            // 重建後重寫 sidecar（剔除已平倉的 stale 條目）。
            self.persist_entry_ts();
            info!(
                strategy = "flash_dip_buy",
                imported, "rebuilt open set + entry_ts from paper_state + checkpoint"
            );
        }
    }

    /// 本策略 Close 確認 → 清開倉集 + entry_ts + 持久化。
    fn on_close_confirmed(&mut self, symbol: &str, _close_price: f64, _close_ts_ms: u64) {
        self.open_symbols.remove(symbol);
        self.pending_entry_expiry.remove(symbol);
        self.entry_ts.remove(symbol);
        self.last_exit_day.remove(symbol);
        self.persist_entry_ts();
    }

    /// 風控強平 → 同步清開倉集 + entry_ts。
    fn on_external_close(&mut self, symbol: &str, _close_price: f64, _close_ts_ms: u64) {
        self.open_symbols.remove(symbol);
        self.pending_entry_expiry.remove(symbol);
        self.entry_ts.remove(symbol);
        self.last_exit_day.remove(symbol);
        self.persist_entry_ts();
    }

    /// Close 被跳過（paper_state 找不到倉位）→ 清開倉集 + entry_ts。
    fn on_close_skipped(&mut self, symbol: &str) {
        self.open_symbols.remove(symbol);
        self.pending_entry_expiry.remove(symbol);
        self.entry_ts.remove(symbol);
        self.last_exit_day.remove(symbol);
        self.persist_entry_ts();
    }

    // ── Phase 3a runtime tuning IPC ──

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: FlashDipBuyUpdateParams =
            serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&FlashDipBuyUpdateParams::param_ranges()).unwrap_or_default()
    }

    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }

    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }

    /// boot 1d REST seed setter：bootstrap 讀 KlineManager 1d buffer 最後收盤後注入。
    /// 為什麼經 trait override 而非 inherent：bootstrap 透過 `dyn Strategy`
    /// （orchestrator.find_strategy_mut）注入，需經 trait dispatch。
    /// leak-free：呼叫端只傳「已收盤的前一 UTC 日收盤價」（非 building bar）。
    fn seed_prior_close(&mut self, symbol: &str, prior_close: f64) {
        if prior_close.is_finite() && prior_close > 0.0 {
            self.prior_close.insert(symbol.to_string(), prior_close);
        }
    }

    /// boot DB seed setter：恢復當日已在交易所 Working 的 entry order，防 restart
    /// 後 producer-side pending cap 低估。
    fn seed_pending_entry(&mut self, symbol: &str, expiry_ms: u64) {
        if !self.is_allowed_symbol(symbol) {
            return;
        }
        let now_wall_ms = openclaw_core::now_ms();
        if expiry_ms <= now_wall_ms {
            return;
        }
        self.pending_entry_expiry
            .insert(symbol.to_string(), expiry_ms);
    }
}
