// MODULE_NOTE
// 模塊用途：M4 Stage 1 Event-Window Analysis Algorithm-B（per W1-B spec §2.2）。
//   3 種 event detector + pre/post window forward return shift 計算 + N >= 30 硬 gate。
//
// 3 detector（Sprint 2 baseline）：
//   - detect_funding_flip_events: sign change + |rate| > 0.01%
//   - detect_liquidation_cascade_events: cascade_size > 5M USD 5min window
//   - detect_large_funding_spike_events: |funding_rate| > 0.1%
//
// 公式（per W1-B spec §2.2.2）：
//   window_pre  = forward_return[t - pre_window .. t - 1m]  (排除 t 本身)
//   window_post = forward_return[t + 1m .. t + post_window] (排除 t 本身)
//   effect      = mean(window_post) - mean(window_pre)
//
// 不變量：
//   - I-4 強制：N < 30 必 EventWindowVerdict::Exploratory（不能 promote）
//   - pre window 必排除 event_t 本身（避免 event 引入 leak）
//   - post window 必從 event_t + 1m 起（event 本身的 bar 屬 transition zone）
//   - 同 symbol 連續 event 在 < 2 × max(pre,post) 內 → 合併為 single event 避雙重計算

use super::types::{EventType, EventWindowResult, EventWindowVerdict};

/// 從 funding_rate 時序中偵測 funding flip event（sign change + magnitude gate）。
///
/// 輸入：funding_rate 時序（按 ts 排序）；
/// 輸出：event index list（指向 funding_rate slice 的 i，代表「flip 發生在 i」）。
///
/// 為什麼 magnitude gate 0.01%：避免在 funding rate 振幅極小的低波動 symbol 產生
/// 噪音 false-positive flip event；per W1-B spec §1.4。
pub fn detect_funding_flip_events(
    funding_rates: &[f64],
    magnitude_gate: f64, // baseline 0.0001 = 0.01%
) -> Vec<usize> {
    let mut events = Vec::new();
    for i in 1..funding_rates.len() {
        let prev = funding_rates[i - 1];
        let cur = funding_rates[i];
        // sign change 條件：prev / cur 異號（不算 0 為「同號」）。
        let sign_change =
            (prev > 0.0 && cur < 0.0) || (prev < 0.0 && cur > 0.0);
        // magnitude gate：current rate 絕對值需 >= 閾值。
        let large_enough = cur.abs() >= magnitude_gate;
        if sign_change && large_enough {
            events.push(i);
        }
    }
    events
}

/// 從 funding_rate 偵測 large spike event（|rate| > magnitude_gate）。
///
/// 為什麼分開 detect：與 flip 不同 — spike 不需要 sign change，
/// 只需 magnitude 超閾值（baseline 0.001 = 0.1% per W1-B spec §2.2.1）。
pub fn detect_large_funding_spike_events(
    funding_rates: &[f64],
    magnitude_gate: f64, // baseline 0.001 = 0.1%
) -> Vec<usize> {
    let mut events = Vec::new();
    for (i, &rate) in funding_rates.iter().enumerate() {
        if rate.abs() >= magnitude_gate {
            events.push(i);
        }
    }
    events
}

/// 從 liquidation 5min cascade size 時序偵測 cascade event。
///
/// 輸入：cascade_size_usd 時序（按 ts 5min 聚合 — caller 預處理）。
///
/// 為什麼 5M USD：W1-B spec §2.2.1 baseline；configurable per config.toml。
pub fn detect_liquidation_cascade_events(
    cascade_size_usd: &[f64],
    cascade_threshold_usd: f64, // baseline 5_000_000.0
) -> Vec<usize> {
    let mut events = Vec::new();
    for (i, &size) in cascade_size_usd.iter().enumerate() {
        if size >= cascade_threshold_usd {
            events.push(i);
        }
    }
    events
}

/// 合併鄰近 event（連續事件在 < 2 × max(pre,post) 內 → 合併單一 event）。
///
/// per W1-B spec §2.2.4 邊界 invariant：避免雙重計算同一 cascade。
pub fn merge_close_events(
    event_indices: &[usize],
    pre_window: usize,
    post_window: usize,
) -> Vec<usize> {
    if event_indices.is_empty() {
        return Vec::new();
    }
    let merge_distance = 2 * pre_window.max(post_window);
    let mut merged = Vec::new();
    let mut last: Option<usize> = None;
    for &idx in event_indices {
        match last {
            Some(prev) if idx - prev < merge_distance => {
                // 合併：保留更早的 event index（first-occurrence semantic）。
            }
            _ => {
                merged.push(idx);
                last = Some(idx);
            }
        }
    }
    merged
}

/// 為單一 event_index 計算 pre/post window forward return shift。
///
/// 公式（per W1-B spec §2.2.2）：
///   pre  = mean(forward_return[event_t - pre_window .. event_t])  排除 event_t 本身
///   post = mean(forward_return[event_t + 1 .. event_t + post_window + 1]) 排除 event_t
///   effect = post - pre
///
/// 為什麼跳過 event bar 本身：event 本身的 bar 屬 transition zone — 含 event 的
/// price action 已包含 event signal，會 leak 進 post window（per W1-B I-1）。
///
/// 不變量：
///   - event_index < pre_window → None（pre 樣本不足）
///   - event_index + post_window + 1 > N → None（post 樣本不足）
///   - forward_return[event_index] 不算入 pre 也不算入 post
pub fn event_window_forward_shift(
    forward_return_bps: &[f64],
    event_index: usize,
    pre_window: usize,
    post_window: usize,
) -> Option<(f64, f64, f64)> {
    let n = forward_return_bps.len();
    if event_index < pre_window || event_index + post_window + 1 > n {
        return None;
    }
    // pre: [event_index - pre_window .. event_index] — 不含 event_index 本身
    let pre_slice = &forward_return_bps[event_index - pre_window..event_index];
    // post: [event_index + 1 .. event_index + post_window + 1] — 不含 event_index 本身
    let post_slice = &forward_return_bps[event_index + 1..event_index + post_window + 1];

    if pre_slice.is_empty() || post_slice.is_empty() {
        return None;
    }

    let pre_mean = pre_slice.iter().sum::<f64>() / pre_slice.len() as f64;
    let post_mean = post_slice.iter().sum::<f64>() / post_slice.len() as f64;
    let effect = post_mean - pre_mean;
    Some((pre_mean, post_mean, effect))
}

/// 對 batch event 算 effect 與 statistical test，產出 EventWindowResult。
///
/// 整合 W1-B spec §2.2.2 effect calculation + §2.2.3 sample gate + §3 Cohen's d。
pub fn analyze_event_window(
    event_type: EventType,
    forward_return_bps: &[f64],
    event_indices: &[usize],
    pre_window: usize,
    post_window: usize,
) -> Option<EventWindowResult> {
    let merged = merge_close_events(event_indices, pre_window, post_window);
    if merged.is_empty() {
        return None;
    }
    let mut pre_means = Vec::with_capacity(merged.len());
    let mut post_means = Vec::with_capacity(merged.len());
    let mut effects = Vec::with_capacity(merged.len());
    for &idx in &merged {
        if let Some((pre_m, post_m, eff)) =
            event_window_forward_shift(forward_return_bps, idx, pre_window, post_window)
        {
            pre_means.push(pre_m);
            post_means.push(post_m);
            effects.push(eff);
        }
    }
    let n_events = effects.len();
    if n_events == 0 {
        return None;
    }
    let pre_mean: f64 = pre_means.iter().sum::<f64>() / n_events as f64;
    let post_mean: f64 = post_means.iter().sum::<f64>() / n_events as f64;
    let effect_bps: f64 = effects.iter().sum::<f64>() / n_events as f64;

    // Cohen's d = effect / pooled_std。
    // 為什麼 pooled：pre/post 同一 event index 下兩 sample，N 一致 →
    // pooled_std = sqrt((var_pre + var_post) / 2)。
    let var_pre = if pre_means.len() > 1 {
        let m = pre_mean;
        pre_means.iter().map(|v| (v - m).powi(2)).sum::<f64>() / pre_means.len() as f64
    } else {
        0.0
    };
    let var_post = if post_means.len() > 1 {
        let m = post_mean;
        post_means.iter().map(|v| (v - m).powi(2)).sum::<f64>() / post_means.len() as f64
    } else {
        0.0
    };
    let pooled_std = ((var_pre + var_post) / 2.0).sqrt();
    let cohens_d = if pooled_std < 1e-15 { 0.0 } else { effect_bps / pooled_std };

    // p-value：用 effect / (pooled_std / sqrt(N)) 作為近似 t-statistic。
    let se = if n_events > 0 && pooled_std > 1e-15 {
        pooled_std / (n_events as f64).sqrt()
    } else {
        f64::INFINITY
    };
    let t_stat = if se.is_finite() && se > 1e-15 {
        effect_bps / se
    } else {
        0.0
    };
    let raw_p = super::cross_correlation::corr_to_p_value(
        t_stat / (n_events as f64 + t_stat * t_stat).sqrt(), // 轉成 r-like for corr_to_p_value reuse
        n_events,
    );

    Some(EventWindowResult {
        event_type,
        n_events,
        pre_window_mean_bps: pre_mean,
        post_window_mean_bps: post_mean,
        effect_bps,
        raw_p_value: raw_p,
        cohens_d,
    })
}

/// Event-window sample-gate verdict — per W1-B spec §2.2.3 + §3.2 I-4。
///
/// 為什麼 30：Mann-Whitney U power > 0.5 at d=0.5 medium effect（per spec）。
/// 為什麼 hard gate 而非 soft warning：避免 N=5 的 spurious 顯著被誤 promote。
pub fn event_window_sample_gate(n_events: usize) -> EventWindowVerdict {
    if n_events < 30 {
        EventWindowVerdict::Exploratory
    } else {
        EventWindowVerdict::PreregisteredCandidate
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detect_funding_flip_basic() {
        // funding [-0.0002, 0.0002, -0.0002] 應 2 個 flip。
        let rates = vec![-0.0002, 0.0002, -0.0002];
        let events = detect_funding_flip_events(&rates, 0.0001);
        assert_eq!(events.len(), 2, "應偵測 2 個 flip");
    }

    #[test]
    fn detect_funding_flip_ignores_small_magnitude() {
        // magnitude 0.00005 < gate 0.0001 → 不計。
        let rates = vec![-0.00005, 0.00005, -0.00005];
        let events = detect_funding_flip_events(&rates, 0.0001);
        assert_eq!(events.len(), 0, "magnitude < gate 不應計入");
    }

    #[test]
    fn detect_large_funding_spike() {
        let rates = vec![0.0005, 0.0015, 0.0008, 0.0020];
        let events = detect_large_funding_spike_events(&rates, 0.001);
        // index 1, 3 應 hit（magnitude >= 0.001）
        assert_eq!(events, vec![1, 3]);
    }

    #[test]
    fn detect_liquidation_cascade() {
        let sizes = vec![1_000_000.0, 6_000_000.0, 3_000_000.0, 10_000_000.0];
        let events = detect_liquidation_cascade_events(&sizes, 5_000_000.0);
        assert_eq!(events, vec![1, 3]);
    }

    #[test]
    fn merge_close_events_collapses_nearby() {
        // events at [10, 12, 50]; window 5 → merge_distance = 10
        // 10 與 12 距離 2 < 10 → 合併為 10；50 距離 50-10=40 > 10 → 保留
        let merged = merge_close_events(&[10, 12, 50], 5, 5);
        assert_eq!(merged, vec![10, 50]);
    }

    #[test]
    fn merge_close_events_keeps_far_events() {
        let merged = merge_close_events(&[10, 100, 200], 5, 5);
        assert_eq!(merged, vec![10, 100, 200]);
    }

    #[test]
    fn event_window_forward_shift_excludes_event_bar() {
        // forward_return 10 個 element：[10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        // event_index = 4（mid），pre_window = 2，post_window = 2
        // pre slice = [event_idx-2..event_idx] = [2..4] = [30, 40] → mean = 35
        // post slice = [event_idx+1..event_idx+1+2] = [5..7] = [60, 70] → mean = 65
        // effect = 65 - 35 = 30；event_idx 50 不算入
        let returns: Vec<f64> = (1..=10).map(|i| (i * 10) as f64).collect();
        let r = event_window_forward_shift(&returns, 4, 2, 2).unwrap();
        assert!((r.0 - 35.0).abs() < 1e-10, "pre mean: {}", r.0);
        assert!((r.1 - 65.0).abs() < 1e-10, "post mean: {}", r.1);
        assert!((r.2 - 30.0).abs() < 1e-10, "effect: {}", r.2);
    }

    #[test]
    fn event_window_insufficient_pre_returns_none() {
        let returns = vec![10.0, 20.0, 30.0, 40.0, 50.0];
        // event_index=1, pre_window=3 → idx < pre_window → None
        assert!(event_window_forward_shift(&returns, 1, 3, 2).is_none());
    }

    #[test]
    fn event_window_insufficient_post_returns_none() {
        let returns = vec![10.0, 20.0, 30.0, 40.0, 50.0];
        // event_index=4, post_window=2 → idx+post+1=7 > 5 → None
        assert!(event_window_forward_shift(&returns, 4, 2, 2).is_none());
    }

    #[test]
    fn sample_gate_n_lt_30_returns_exploratory() {
        // I-4 不變量：N < 30 必 Exploratory。
        for n in [0, 1, 5, 10, 20, 29] {
            assert_eq!(
                event_window_sample_gate(n),
                EventWindowVerdict::Exploratory,
                "n={} 必為 Exploratory",
                n
            );
        }
    }

    #[test]
    fn sample_gate_n_ge_30_returns_preregistered_candidate() {
        for n in [30, 50, 100, 1000] {
            assert_eq!(
                event_window_sample_gate(n),
                EventWindowVerdict::PreregisteredCandidate,
                "n={} 必為 PreregisteredCandidate",
                n
            );
        }
    }
}
