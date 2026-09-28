//! Per-subscription Bybit book. Deltas describe changed levels, never a BBO.
use openclaw_types::{PriceEvent, PriceEventKind};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Default)]
pub(super) struct Orderbook {
    // Positive finite IEEE-754 bits have numeric ordering; no float Ord dependency.
    bids: BTreeMap<u64, f64>,
    asks: BTreeMap<u64, f64>,
    update_id: u64,
    seq: u64,
    ts: u64,
}

impl Orderbook {
    /// Err invalidates the subscription; Ok(None) is a duplicate/older delta.
    pub(super) fn apply(
        &mut self,
        message: &Value,
        topic: &str,
        record: bool,
    ) -> Result<Option<PriceEvent>, &'static str> {
        let parts: Vec<_> = topic.split('.').collect();
        if parts.len() != 3 {
            return Err("invalid topic");
        }
        let depth: usize = parts[1].parse().map_err(|_| "invalid depth")?;
        if depth == 0 || depth > 1000 {
            return Err("unsupported depth");
        }
        let symbol = parts[2];
        let obj = &message["data"];
        if obj["s"].as_str() != Some(symbol) {
            return Err("symbol mismatch");
        }
        let ts = number(&message["ts"])
            .filter(|v| *v > 0)
            .ok_or("missing exchange time")?;
        let u = number(&obj["u"])
            .filter(|v| *v > 0)
            .ok_or("missing update id")?;
        let seq = number(&obj["seq"]).ok_or("missing sequence")?;
        let snapshot = match message["type"].as_str() {
            Some("snapshot") => true,
            Some("delta") => false,
            _ => return Err("invalid message type"),
        };
        if !snapshot {
            if self.update_id == 0 || u == 1 {
                return Err("snapshot required");
            }
            // Cross-sequence can jump: it is not a contiguous per-topic counter.
            if u <= self.update_id || seq < self.seq || ts < self.ts {
                return Ok(None);
            }
        }
        let bids = levels(&obj["b"])?;
        let asks = levels(&obj["a"])?;
        if snapshot {
            self.bids.clear();
            self.asks.clear();
        }
        apply_levels(&mut self.bids, &bids);
        apply_levels(&mut self.asks, &asks);
        while self.bids.len() > depth {
            self.bids.pop_first();
        }
        while self.asks.len() > depth {
            self.asks.pop_last();
        }
        let bid = self
            .bids
            .last_key_value()
            .map(|(p, _)| f64::from_bits(*p))
            .ok_or("empty bids")?;
        let ask = self
            .asks
            .first_key_value()
            .map(|(p, _)| f64::from_bits(*p))
            .ok_or("empty asks")?;
        if bid >= ask {
            return Err("crossed book");
        }
        self.update_id = u;
        self.seq = seq;
        self.ts = ts;
        let mut event = PriceEvent::new(symbol.to_owned(), bid / 2.0 + ask / 2.0, ts);
        event.event_kind = Some(PriceEventKind::Orderbook);
        event.bid_price = bid;
        event.ask_price = ask;
        let bids5: Vec<_> = self
            .bids
            .iter()
            .rev()
            .take(5)
            .map(|(p, q)| (f64::from_bits(*p), *q))
            .collect();
        let asks5: Vec<_> = self
            .asks
            .iter()
            .take(5)
            .map(|(p, q)| (f64::from_bits(*p), *q))
            .collect();
        event.metadata.insert("type".into(), "orderbook".into());
        event
            .metadata
            .insert("bids5".into(), serde_json::to_string(&bids5).unwrap());
        event
            .metadata
            .insert("asks5".into(), serde_json::to_string(&asks5).unwrap());
        event.bids5 = Some(bids5);
        event.asks5 = Some(asks5);
        // Recorder receives raw changes, trading receives reconstructed top levels.
        if record {
            event.ob_msg_type = message["type"].as_str().map(str::to_owned);
            event.ob_changed_bids = Some(bids);
            event.ob_changed_asks = Some(asks);
            event.ob_update_id = Some(u);
            event.ob_seq = Some(seq);
        }
        Ok(Some(event))
    }
}
fn number(value: &Value) -> Option<u64> {
    value.as_u64().or_else(|| value.as_str()?.parse().ok())
}
fn levels(value: &Value) -> Result<Vec<(f64, f64)>, &'static str> {
    value
        .as_array()
        .ok_or("missing levels")?
        .iter()
        .map(|v| {
            let p: f64 = v[0]
                .as_str()
                .ok_or("invalid price")?
                .parse()
                .map_err(|_| "invalid price")?;
            let q: f64 = v[1]
                .as_str()
                .ok_or("invalid quantity")?
                .parse()
                .map_err(|_| "invalid quantity")?;
            if !p.is_finite() || p <= 0.0 || !q.is_finite() || q < 0.0 {
                return Err("invalid level");
            }
            Ok((p, q))
        })
        .collect()
}
fn apply_levels(book: &mut BTreeMap<u64, f64>, levels: &[(f64, f64)]) {
    for &(price, qty) in levels {
        if qty == 0.0 {
            book.remove(&price.to_bits());
        } else {
            book.insert(price.to_bits(), qty);
        }
    }
}
