//! Feature collector — captures IndicatorSnapshot as a flat feature vector for ML/DB.
//! 特徵收集器 — 將 IndicatorSnapshot 捕獲為扁平特徵向量，供 ML/DB 使用。
//!
//! MODULE_NOTE (EN): Provides FeatureSnapshot struct with to_feature_vector() that flattens
//!   16 indicators into a 34-dimension f32 array (31 scalars + 2 regime enums + 1 price).
//!   Ring buffer (VecDeque, cap 3000) for in-memory retention. try_send() pattern for
//!   non-blocking channel dispatch from tick_pipeline.
//! MODULE_NOTE (中): 提供 FeatureSnapshot 結構體及 to_feature_vector()，將 16 個指標
//!   扁平化為 34 維 f32 陣列（31 個標量 + 2 個 regime 枚舉整數編碼 + 1 個價格）。
//!   環形緩衝區（VecDeque，容量 3000）用於內存保留。
//!   使用 try_send() 模式從 tick_pipeline 非阻塞發送到通道。

use openclaw_core::indicators::IndicatorSnapshot;
use std::collections::VecDeque;

/// Feature vector dimension count (F4 audit: 31 scalars + 2 regime enums + 1 donchian width + price = 34).
/// 特徵向量維度數。
pub const FEATURE_DIM: usize = 34;

/// Default ring buffer capacity (~5 minutes at 10 ticks/sec).
/// 預設環形緩衝區容量（約 5 分鐘 × 10 ticks/sec）。
pub const DEFAULT_BUFFER_CAPACITY: usize = 3000;

/// Regime string → integer encoding for feature vector.
/// Regime 字符串 → 整數編碼。
fn encode_regime(regime: &str) -> f32 {
    match regime {
        "trending" | "Trending" => 1.0,
        "mean_reverting" | "MeanReverting" => 2.0,
        "random_walk" | "RandomWalk" => 3.0,
        _ => 0.0, // unknown
    }
}

/// Volatility regime string → integer encoding.
/// 波動率 regime 字符串 → 整數編碼。
fn encode_vol_regime(regime: &str) -> f32 {
    match regime {
        "low" | "Low" => 1.0,
        "medium" | "Medium" => 2.0,
        "high" | "High" => 3.0,
        _ => 0.0,
    }
}

/// Snapshot of features at a single tick, ready for DB write.
/// 單一 tick 的特徵快照，用於 DB 寫入。
#[derive(Debug, Clone)]
pub struct FeatureSnapshot {
    pub symbol: String,
    pub timeframe: String,
    pub ts_ms: u64,
    pub price: f64,
    pub volume_24h: f64,
    pub indicators: IndicatorSnapshot,
    pub feature_version: String,
}

impl FeatureSnapshot {
    /// Create from tick data and indicators.
    /// 從 tick 數據和指標創建。
    pub fn new(
        symbol: String,
        ts_ms: u64,
        price: f64,
        volume_24h: f64,
        indicators: IndicatorSnapshot,
        feature_version: String,
    ) -> Self {
        Self {
            symbol,
            timeframe: "1m".into(),
            ts_ms,
            price,
            volume_24h,
            indicators,
            feature_version,
        }
    }

    /// Flatten indicators into a REAL[] for features.online_latest.
    /// 31 f64 scalars + 2 regime enums (integer-encoded) + 1 price = 34 dimensions.
    /// 將指標扁平化為 REAL[] 用於 features.online_latest。
    /// 31 個 f64 標量 + 2 個 regime 枚舉（整數編碼）+ 1 個價格 = 34 維。
    pub fn to_feature_vector(&self) -> Vec<f32> {
        let ind = &self.indicators;
        let mut v = Vec::with_capacity(FEATURE_DIM);

        // 1-2: SMA
        v.push(ind.sma_20.unwrap_or(0.0) as f32);
        v.push(ind.sma_50.unwrap_or(0.0) as f32);
        // 3-4: EMA
        v.push(ind.ema_12.unwrap_or(0.0) as f32);
        v.push(ind.ema_26.unwrap_or(0.0) as f32);
        // 5: RSI
        v.push(ind.rsi_14.unwrap_or(50.0) as f32);
        // 6-8: MACD
        if let Some(ref m) = ind.macd {
            v.push(m.macd as f32);
            v.push(m.signal as f32);
            v.push(m.histogram as f32);
        } else {
            v.extend_from_slice(&[0.0_f32; 3]);
        }
        // 9-13: Bollinger
        if let Some(ref b) = ind.bollinger {
            v.push(b.upper as f32);
            v.push(b.middle as f32);
            v.push(b.lower as f32);
            v.push(b.bandwidth as f32);
            v.push(b.percent_b as f32);
        } else {
            v.extend_from_slice(&[0.0_f32; 5]);
        }
        // 14-15: ATR(14)
        if let Some(ref a) = ind.atr_14 {
            v.push(a.atr as f32);
            v.push(a.atr_percent as f32);
        } else {
            v.extend_from_slice(&[0.0_f32; 2]);
        }
        // 16-17: ATR(5)
        if let Some(ref a) = ind.atr_5 {
            v.push(a.atr as f32);
            v.push(a.atr_percent as f32);
        } else {
            v.extend_from_slice(&[0.0_f32; 2]);
        }
        // 18-19: Stochastic
        if let Some(ref s) = ind.stochastic {
            v.push(s.k as f32);
            v.push(s.d as f32);
        } else {
            v.extend_from_slice(&[0.0_f32; 2]);
        }
        // 20-21: KAMA
        if let Some(ref k) = ind.kama {
            v.push(k.kama as f32);
            v.push(k.efficiency_ratio as f32);
        } else {
            v.extend_from_slice(&[0.0_f32; 2]);
        }
        // 22-24: ADX
        if let Some(ref a) = ind.adx {
            v.push(a.adx as f32);
            v.push(a.plus_di as f32);
            v.push(a.minus_di as f32);
        } else {
            v.extend_from_slice(&[0.0_f32; 3]);
        }
        // 25-26: Hurst + regime_id
        if let Some(ref h) = ind.hurst {
            v.push(h.hurst as f32);
            v.push(encode_regime(&h.regime));
        } else {
            v.extend_from_slice(&[0.5_f32, 0.0]); // 0.5 = random walk default
        }
        // 27-28: EWMA vol + vol_regime_id
        if let Some(ref e) = ind.ewma_vol {
            v.push(e.ewma_vol as f32);
            v.push(encode_vol_regime(&e.vol_regime));
        } else {
            v.extend_from_slice(&[0.0_f32; 2]);
        }
        // 29: Volume ratio
        v.push(ind.volume_ratio.unwrap_or(1.0) as f32);
        // 30-33: Donchian (upper, lower, middle, width)
        if let Some(ref d) = ind.donchian {
            v.push(d.upper as f32);
            v.push(d.lower as f32);
            v.push(d.middle as f32);
            v.push(d.width as f32);
        } else {
            v.extend_from_slice(&[0.0_f32; 4]);
        }
        // 34: Current price
        v.push(self.price as f32);

        debug_assert_eq!(v.len(), FEATURE_DIM, "feature vector dimension mismatch");
        v
    }
}

/// Ring buffer for FeatureSnapshots (drop-oldest on overflow).
/// 特徵快照環形緩衝區（溢出時丟棄最舊）。
pub struct FeatureBuffer {
    buffer: VecDeque<FeatureSnapshot>,
    capacity: usize,
    dropped: u64,
}

impl FeatureBuffer {
    /// Create with specified capacity.
    /// 以指定容量創建。
    pub fn new(capacity: usize) -> Self {
        Self {
            buffer: VecDeque::with_capacity(capacity.min(4096)),
            capacity,
            dropped: 0,
        }
    }

    /// Push a snapshot, dropping oldest if at capacity.
    /// 推入快照，達到容量時丟棄最舊的。
    pub fn push(&mut self, snapshot: FeatureSnapshot) {
        if self.buffer.len() >= self.capacity {
            self.buffer.pop_front();
            self.dropped += 1;
        }
        self.buffer.push_back(snapshot);
    }

    /// Current buffer length / 當前緩衝區長度
    pub fn len(&self) -> usize {
        self.buffer.len()
    }

    /// Is buffer empty / 緩衝區是否為空
    pub fn is_empty(&self) -> bool {
        self.buffer.is_empty()
    }

    /// Total dropped count / 總丟棄數
    pub fn dropped(&self) -> u64 {
        self.dropped
    }

    /// Drain all buffered snapshots / 排空所有緩衝的快照
    pub fn drain(&mut self) -> Vec<FeatureSnapshot> {
        self.buffer.drain(..).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_snapshot(symbol: &str, ts: u64) -> FeatureSnapshot {
        FeatureSnapshot::new(
            symbol.into(), ts, 50000.0, 1e9,
            IndicatorSnapshot::default(), "v1.0".into(),
        )
    }

    #[test]
    fn test_feature_vector_dimension() {
        let snap = make_snapshot("BTCUSDT", 1000);
        let vec = snap.to_feature_vector();
        assert_eq!(vec.len(), FEATURE_DIM);
    }

    #[test]
    fn test_feature_vector_with_full_indicators() {
        use openclaw_core::indicators::*;
        let ind = IndicatorSnapshot {
            sma_20: Some(50000.0),
            sma_50: Some(49000.0),
            ema_12: Some(50100.0),
            ema_26: Some(49800.0),
            rsi_14: Some(65.0),
            macd: Some(MacdResult { macd: 300.0, signal: 250.0, histogram: 50.0 }),
            bollinger: Some(BollingerResult { upper: 51000.0, middle: 50000.0, lower: 49000.0, bandwidth: 0.04, percent_b: 0.75 }),
            atr_14: Some(AtrResult { atr: 500.0, atr_percent: 1.0 }),
            atr_5: Some(AtrResult { atr: 600.0, atr_percent: 1.2 }),
            stochastic: Some(StochResult { k: 70.0, d: 65.0 }),
            kama: Some(KamaResult { kama: 50050.0, efficiency_ratio: 0.8 }),
            adx: Some(AdxResult { adx: 30.0, plus_di: 25.0, minus_di: 15.0 }),
            hurst: Some(HurstResult { hurst: 0.65, regime: "trending".into() }),
            ewma_vol: Some(EwmaVolResult { ewma_vol: 0.02, vol_regime: "medium".into() }),
            volume_ratio: Some(1.5),
            donchian: Some(DonchianResult { upper: 51500.0, lower: 48500.0, middle: 50000.0, width: 3000.0 }),
        };
        let snap = FeatureSnapshot::new("BTCUSDT".into(), 1000, 50000.0, 1e9, ind, "v1.0".into());
        let vec = snap.to_feature_vector();
        assert_eq!(vec.len(), FEATURE_DIM);
        // Check some specific values (0-indexed)
        assert!((vec[0] - 50000.0).abs() < 0.01); // sma_20
        assert!((vec[4] - 65.0).abs() < 0.01);    // rsi_14
        assert!((vec[24] - 0.65).abs() < 0.01);   // hurst (idx 24)
        assert!((vec[25] - 1.0).abs() < 0.01);    // hurst regime = trending = 1.0 (idx 25)
        assert!((vec[FEATURE_DIM - 1] - 50000.0).abs() < 0.01); // last = price
    }

    #[test]
    fn test_ring_buffer_drop_oldest() {
        let mut buf = FeatureBuffer::new(3);
        buf.push(make_snapshot("A", 1));
        buf.push(make_snapshot("B", 2));
        buf.push(make_snapshot("C", 3));
        assert_eq!(buf.len(), 3);
        assert_eq!(buf.dropped(), 0);

        buf.push(make_snapshot("D", 4));
        assert_eq!(buf.len(), 3);
        assert_eq!(buf.dropped(), 1);

        let drained = buf.drain();
        assert_eq!(drained.len(), 3);
        assert_eq!(drained[0].ts_ms, 2); // oldest is B (A was dropped)
    }

    #[test]
    fn test_ring_buffer_at_capacity_3000() {
        let mut buf = FeatureBuffer::new(DEFAULT_BUFFER_CAPACITY);
        for i in 0..DEFAULT_BUFFER_CAPACITY + 100 {
            buf.push(make_snapshot("X", i as u64));
        }
        assert_eq!(buf.len(), DEFAULT_BUFFER_CAPACITY);
        assert_eq!(buf.dropped(), 100);
    }

    #[test]
    fn test_regime_encoding() {
        assert_eq!(encode_regime("trending"), 1.0);
        assert_eq!(encode_regime("mean_reverting"), 2.0);
        assert_eq!(encode_regime("random_walk"), 3.0);
        assert_eq!(encode_regime("unknown"), 0.0);
    }

    #[test]
    fn test_vol_regime_encoding() {
        assert_eq!(encode_vol_regime("low"), 1.0);
        assert_eq!(encode_vol_regime("medium"), 2.0);
        assert_eq!(encode_vol_regime("high"), 3.0);
        assert_eq!(encode_vol_regime(""), 0.0);
    }
}
