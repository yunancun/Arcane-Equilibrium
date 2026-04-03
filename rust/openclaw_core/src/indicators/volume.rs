//! Volume indicators: VolumeRatio.
//! 成交量指標：量比。

use super::kahan_sum;

// ═══════════════════════════════════════════════════════════════════════════════
// VolumeRatio / 量比
// ═══════════════════════════════════════════════════════════════════════════════

/// Volume ratio: current volume / average volume over period [K].
/// 量比：當前成交量 / 週期內平均成交量 [K]。
pub fn volume_ratio(volume: &[f64], period: usize) -> Option<f64> {
    if period == 0 || volume.len() < period + 1 {
        return None;
    }
    let n = volume.len();
    let avg_window = &volume[n - period - 1..n - 1];
    let avg = kahan_sum(avg_window) / period as f64;
    let current = volume[n - 1];
    if avg < 1e-15 {
        return None;
    }
    Some(current / avg)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_volume_ratio_basic() {
        let vol = [100.0, 100.0, 100.0, 100.0, 200.0];
        let r = volume_ratio(&vol, 4).unwrap();
        assert!((r - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_volume_ratio_equal() {
        let vol = vec![50.0; 10];
        let r = volume_ratio(&vol, 5).unwrap();
        assert!((r - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_volume_ratio_edge() {
        assert!(volume_ratio(&[1.0], 1).is_none()); // need period+1
        assert!(volume_ratio(&[], 1).is_none());
        // Zero average volume
        let vol = [0.0, 0.0, 0.0, 0.0, 100.0];
        assert!(volume_ratio(&vol, 4).is_none());
    }
}
