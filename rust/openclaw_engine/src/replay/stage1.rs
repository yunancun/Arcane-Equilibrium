//! R8 隔離回放：選用成交排程、單調選擇器與穩定稽核索引。
use super::{runner::IsolatedPipeline, MarketEvent, SimulatedFill};
use crate::{order_manager::TimeInForce, strategies::StrategyAction};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Clone, Copy, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionTiming {
    #[default]
    CurrentBarClose,
    NextSymbolOpen,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(tag = "action", deny_unknown_fields)]
pub enum Selector {
    #[serde(rename = "NO_OP")]
    NoOp {},
    #[serde(rename = "VETO")]
    Veto {},
    #[serde(rename = "SIZE_DOWN")]
    SizeDown { size_factor: f64 },
}

impl Default for Selector {
    fn default() -> Self {
        Self::NoOp {}
    }
}

#[derive(Debug, Clone, Default, Deserialize)]
struct EventExtension {
    ts_ms: i64,
    symbol: String,
    #[serde(default)]
    selector_decision: Option<Selector>,
    #[serde(default)]
    execution_quote_at_open: bool,
}

/// 附加資料與既有載入器按原始行序對齊，不改公開 MarketEvent 結構。
#[derive(Debug, Clone)]
pub struct Stage1Config {
    timing: ExecutionTiming,
    events: Vec<EventExtension>,
    enabled: bool,
}
impl Stage1Config {
    pub fn enabled(&self) -> bool {
        self.enabled
    }
    pub fn from_fixture(
        path: &Path,
        events: &[MarketEvent],
        timing: ExecutionTiming,
        latency_ms: Option<u64>,
        metadata: bool,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        #[derive(Deserialize)]
        struct Envelope {
            events: Vec<EventExtension>,
        }
        let extra: Envelope = serde_json::from_slice(&std::fs::read(path)?)?;
        if extra.events.len() != events.len() {
            return Err("stage1 fixture row mismatch".into());
        }
        let next = timing == ExecutionTiming::NextSymbolOpen;
        if next && latency_ms.unwrap_or(0) != 0 {
            return Err("next_symbol_open requires zero latency".into());
        }
        let mut last = HashMap::new();
        for (row, event) in extra.events.iter().zip(events) {
            if row.ts_ms != event.ts_ms || row.symbol != event.symbol {
                return Err("stage1 fixture identity mismatch".into());
            }
            if let Some(Selector::SizeDown { size_factor }) = row.selector_decision {
                if !size_factor.is_finite() || size_factor <= 0.0 || size_factor > 1.0 {
                    return Err("SIZE_DOWN size_factor must be finite in (0,1]".into());
                }
            }
            if next {
                if last
                    .insert(&event.symbol, event.ts_ms)
                    .is_some_and(|ts| ts >= event.ts_ms)
                {
                    return Err(
                        "next_symbol_open requires strictly increasing per-symbol timestamps"
                            .into(),
                    );
                }
                if !event.open.is_finite() || event.open <= 0.0 {
                    return Err("next open must be positive finite".into());
                }
                if [
                    event.best_bid,
                    event.best_ask,
                    event.bid_size,
                    event.ask_size,
                    event.bid_depth_5,
                    event.ask_depth_5,
                ]
                .iter()
                .any(Option::is_some)
                    && !row.execution_quote_at_open
                {
                    return Err(
                        "next-event quotes/depth require execution_quote_at_open=true".into(),
                    );
                }
            }
        }
        let enabled =
            next || metadata || extra.events.iter().any(|e| e.selector_decision.is_some());
        Ok(Self {
            timing,
            events: extra.events,
            enabled,
        })
    }
}

#[derive(Debug)]
struct Pending {
    action: StrategyAction,
    audit_index: usize,
    atr: f64,
    turnover: Option<f64>,
    bound_side: Option<bool>,
    bound_generation: u64,
}
impl Pending {
    fn symbol(&self) -> &str {
        match &self.action {
            StrategyAction::Open(i) => &i.symbol,
            StrategyAction::Close { symbol, .. } => symbol,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ActionAudit {
    action_id: String,
    trace_index: usize,
    action_index: usize,
    signal_event_index: usize,
    signal_ts_ms: i64,
    signal_symbol: String,
    target_symbol: String,
    action_kind: String,
    baseline_accepted_qty: Option<f64>,
    requested_qty: Option<f64>,
    filled_qty: f64,
    execution_event_index: Option<usize>,
    execution_ts_ms: Option<i64>,
    selector: Selector,
    selector_applied: bool,
    disposition: String,
    fill_indices: Vec<usize>,
}
#[derive(Debug)]
pub(super) struct Stage1State {
    config: Stage1Config,
    pending: Vec<Pending>,
    audits: Vec<ActionAudit>,
    end_ts: Option<i64>,
    position_generation: HashMap<String, u64>,
}

impl IsolatedPipeline {
    pub fn with_stage1(mut self, config: Stage1Config) -> Result<Self, Box<dyn std::error::Error>> {
        if config.timing == ExecutionTiming::NextSymbolOpen
            && self.execution_latency_ms.unwrap_or(0) != 0
        {
            return Err("next_symbol_open requires zero pipeline latency".into());
        }
        if config.enabled {
            let end_ts = config.events.iter().map(|e| e.ts_ms).max();
            self.stage1 = Some(Stage1State {
                config,
                pending: Vec::new(),
                audits: Vec::new(),
                end_ts,
                position_generation: HashMap::new(),
            });
        }
        Ok(self)
    }
    pub fn stage1_metadata(&self) -> Option<Value> {
        self.stage1.as_ref().map(|state| {
            json!({
                "execution_timing": state.config.timing, "replay_end_ts_ms": state.end_ts,
                "action_audit": state.audits,
            })
        })
    }
    pub(super) fn stage1_execute_pending(&mut self, event_index: usize, event: &MarketEvent) {
        let Some(state) = self.stage1.as_mut() else {
            return;
        };
        let pending = std::mem::take(&mut state.pending);
        for item in pending {
            if item.symbol() == event.symbol {
                self.stage1_fill(item, event_index, event, true);
            } else {
                self.stage1.as_mut().unwrap().pending.push(item);
            }
        }
    }
    pub(super) fn stage1_submit(
        &mut self,
        event_index: usize,
        action_index: usize,
        trace_index: usize,
        event: &MarketEvent,
        atr: f64,
        action: StrategyAction,
    ) {
        let bound_side = match &action {
            StrategyAction::Close { symbol, .. } => self
                .paper_snapshot
                .as_ref()
                .and_then(|s| s.get_position(symbol))
                .map(|p| p.is_long),
            StrategyAction::Open(intent) => self
                .paper_snapshot
                .as_ref()
                .and_then(|s| s.get_position(&intent.symbol))
                .filter(|p| p.is_long != intent.is_long)
                .map(|p| p.is_long),
        };
        let state = self.stage1.as_mut().unwrap();
        let selector = state.config.events[event_index]
            .selector_decision
            .clone()
            .unwrap_or_default();
        let next = state.config.timing == ExecutionTiming::NextSymbolOpen;
        let index = state.audits.len();
        state.audits.push(ActionAudit {
            action_id: format!("{event_index}:{action_index}"),
            trace_index,
            action_index,
            signal_event_index: event_index,
            signal_ts_ms: event.ts_ms,
            signal_symbol: event.symbol.clone(),
            target_symbol: match &action {
                StrategyAction::Open(i) => i.symbol.clone(),
                StrategyAction::Close { symbol, .. } => symbol.clone(),
            },
            action_kind: if matches!(action, StrategyAction::Open(_)) {
                "Open"
            } else {
                "Close"
            }
            .into(),
            baseline_accepted_qty: None,
            requested_qty: None,
            filled_qty: 0.0,
            execution_event_index: None,
            execution_ts_ms: None,
            selector: selector.clone(),
            selector_applied: false,
            disposition: "pending".into(),
            fill_indices: Vec::new(),
        });
        let symbol = match &action {
            StrategyAction::Open(i) => &i.symbol,
            StrategyAction::Close { symbol, .. } => symbol,
        };
        let bound_generation = *state.position_generation.get(symbol).unwrap_or(&0);
        let item = Pending {
            action,
            audit_index: index,
            atr,
            turnover: self.volume_24h,
            bound_side,
            bound_generation,
        };
        if let StrategyAction::Open(intent) = &item.action {
            if next
                && (!intent.order_type.eq_ignore_ascii_case("market")
                    || intent.limit_price.is_some()
                    || matches!(intent.time_in_force, Some(TimeInForce::PostOnly)))
            {
                self.stage1_reject(&item, event.ts_ms, event.close, "unsupported_nonmarket");
                return;
            }
            if bound_side.is_none() && matches!(selector, Selector::Veto { .. }) {
                self.stage1.as_mut().unwrap().audits[index].selector_applied = true;
                self.stage1_reject(&item, event.ts_ms, event.close, "selector_veto");
                return;
            }
            if next
                && self.stage1.as_ref().unwrap().pending.iter().any(|p| {
                    p.symbol() == intent.symbol && matches!(p.action, StrategyAction::Open(_))
                })
            {
                self.stage1_reject(&item, event.ts_ms, event.close, "pending_open_exists");
                return;
            }
        }
        if next {
            self.stage1.as_mut().unwrap().pending.push(item);
        } else {
            self.stage1_fill(item, event_index, event, false);
        }
    }
    fn stage1_fill(&mut self, item: Pending, event_index: usize, event: &MarketEvent, next: bool) {
        let price = if next { event.open } else { event.close };
        let current_pos = self
            .paper_snapshot
            .as_ref()
            .and_then(|s| s.get_position(item.symbol()))
            .cloned();
        let audit = &mut self.stage1.as_mut().unwrap().audits[item.audit_index];
        audit.execution_event_index = Some(event_index);
        audit.execution_ts_ms = Some(event.ts_ms);
        let selector = audit.selector.clone();
        if next {
            if let Some(snap) = self.paper_snapshot.as_mut() {
                snap.latest_price = Some(price);
                snap.latest_price_by_symbol
                    .insert(event.symbol.clone(), price);
            }
            // 滑點與 ATR 僅使用訊號當時已知資料，不能偷看本事件收盤。
            self.volume_24h = item.turnover;
        }
        let generation = *self
            .stage1
            .as_ref()
            .unwrap()
            .position_generation
            .get(item.symbol())
            .unwrap_or(&0);
        if item.bound_side.is_some()
            && (current_pos.as_ref().map(|p| p.is_long) != item.bound_side
                || generation != item.bound_generation)
        {
            self.stage1_reject(&item, event.ts_ms, price, "reduction_position_changed");
            return;
        }
        let first_fill = self.fills.len();
        self.stage1_accepted_qty = None;
        let tier = self.fixture_tier_label_for_stage1();
        match &item.action {
            StrategyAction::Open(intent) => {
                let reducing = current_pos.as_ref().filter(|p| p.is_long != intent.is_long);
                if reducing.is_none() {
                    self.stage1.as_mut().unwrap().audits[item.audit_index].selector_applied = true;
                    if matches!(selector, Selector::Veto { .. }) {
                        self.stage1_reject(&item, event.ts_ms, price, "selector_veto");
                        return;
                    }
                }
                let scale = if reducing.is_some() {
                    1.0
                } else {
                    match selector {
                        Selector::SizeDown { size_factor } => size_factor,
                        _ => 1.0,
                    }
                };
                self.stage1_quantity = Some((scale, reducing.map(|p| p.qty)));
                self.process_open_intent(
                    intent,
                    event.ts_ms,
                    price,
                    event.best_bid,
                    event.best_ask,
                    event.bid_size,
                    event.ask_size,
                    event.bid_depth_5,
                    event.ask_depth_5,
                    item.atr,
                    &tier,
                );
                self.stage1_quantity = None;
            }
            StrategyAction::Close { symbol, .. } => {
                // 訊號時不存在倉位的 Close 不得平掉後來才出現的倉位。
                if item.bound_side.is_none() {
                    self.stage1_reject(&item, event.ts_ms, price, "close_no_position");
                    return;
                }
                self.process_close_intent(
                    symbol,
                    event.ts_ms,
                    price,
                    event.best_bid,
                    event.best_ask,
                    event.bid_size,
                    event.ask_size,
                    event.bid_depth_5,
                    event.ask_depth_5,
                    &tier,
                );
            }
        }
        // 同方向重新開出的倉位也屬另一世代，舊 Close 不得誤平新倉。
        if current_pos.is_none()
            && self
                .paper_snapshot
                .as_ref()
                .and_then(|s| s.get_position(item.symbol()))
                .is_some()
        {
            *self
                .stage1
                .as_mut()
                .unwrap()
                .position_generation
                .entry(item.symbol().to_owned())
                .or_default() += 1;
        }
        let audit = &mut self.stage1.as_mut().unwrap().audits[item.audit_index];
        audit.baseline_accepted_qty = self.stage1_accepted_qty;
        audit.requested_qty = self.fills.get(first_fill).map(|f| f.requested_qty);
        audit.filled_qty = self.fills[first_fill..].iter().map(|f| f.qty).sum();
        audit.fill_indices = (first_fill..self.fills.len()).collect();
        audit.disposition = self.last_action.clone();
    }
    fn stage1_reject(&mut self, item: &Pending, ts_ms: i64, price: f64, reason: &str) {
        let is_long = match &item.action {
            StrategyAction::Open(i) => i.is_long,
            _ => !item.bound_side.unwrap_or(true),
        };
        let index = self.fills.len();
        self.fills.push(SimulatedFill {
            ts_ms,
            symbol: item.symbol().to_owned(),
            side: if is_long { "long" } else { "short" }.into(),
            qty: 0.0,
            requested_qty: 0.0,
            fill_ratio: 0.0,
            fill_status: reason.into(),
            price,
            evidence_source_tier: self.fixture_tier_label_for_stage1(),
            fee: 0.0,
            fee_rate: 0.0,
            slippage_bps: 0.0,
            liquidity_role: "none".into(),
            partial_fill_model_status: "not_evaluated".into(),
            depth_available_qty: None,
            latency_ms: None,
            effective_ts_ms: Some(ts_ms),
        });
        let audit = &mut self.stage1.as_mut().unwrap().audits[item.audit_index];
        audit.disposition = reason.into();
        audit.fill_indices.push(index);
        self.last_action = format!("{reason}:{}", item.symbol());
    }
    pub(super) fn stage1_expire(&mut self) {
        let Some(state) = self.stage1.as_mut() else {
            return;
        };
        let items = std::mem::take(&mut state.pending);
        for item in items {
            let ts = self.stage1.as_ref().unwrap().audits[item.audit_index].signal_ts_ms;
            self.stage1_reject(&item, ts, 0.0, "expired_no_next_event");
        }
    }
}

/// 只有選用擴充才改寫 JSON；舊報告序列化路徑保持原樣。
pub fn extend_report(
    path: &Path,
    metadata: Option<Value>,
    provenance: Option<&Value>,
    overrides: Option<&Value>,
) -> Result<(), Box<dyn std::error::Error>> {
    if metadata.is_none() && provenance.is_none() && overrides.is_none() {
        return Ok(());
    }
    let mut report: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    if let Some(meta) = metadata {
        if let Some(audits) = meta["action_audit"].as_array() {
            for audit in audits {
                let ti = audit["trace_index"].as_u64().unwrap() as usize;
                let ai = audit["action_index"].as_u64().unwrap() as usize;
                if let Some(action) = report["result"]["decision_traces"]
                    .get_mut(ti)
                    .and_then(|t| t["actions_emitted"].get_mut(ai))
                {
                    action["replay_audit"] = audit.clone();
                }
                for fi in audit["fill_indices"].as_array().unwrap() {
                    report["result"]["fills"][fi.as_u64().unwrap() as usize]["replay_audit"] =
                        audit.clone();
                }
            }
        }
        report["stage1"] = meta;
    }
    if let Some(source) = provenance {
        report["parameter_provenance"] = source.clone();
    }
    if let Some(overrides) = overrides {
        report["parameter_overrides"] = overrides.clone();
    }
    std::fs::write(path, serde_json::to_vec_pretty(&report)?)?;
    Ok(())
}
