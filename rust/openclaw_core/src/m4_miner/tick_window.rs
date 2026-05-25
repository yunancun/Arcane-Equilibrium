// MODULE_NOTE
// 模塊用途：M4 Stage 1 tick / bar window aggregator — 高吞吐量 in-memory
//   sliding window 結構，為 hot-path rolling statistics 提供 O(1) 增量更新。
//
// 為什麼需要：W1-B spec §5.1 預估 1m bar 90d × 25 symbol = 3.24M row 單 batch；
//   naive O(N×W) rolling 計算過慢。本 aggregator 提供 push-pop 模式，
//   每次 push 觸發 O(1) running sum / running sum-of-squares 增量更新。
//
// 函數契約：
//   - new(capacity) - 建構固定容量 ring buffer
//   - push(value) - 推入新值，若達 capacity 則 evict 最舊 value 並返回它
//   - mean() / std() / size() - O(1) 查詢
//
// 不變量：
//   - capacity = 0 視為 disabled aggregator（一切 query 回 None）
//   - 增量 sum 採 Kahan 補償降低 catastrophic cancellation 風險
//     （與 openclaw_core::indicators::kahan_sum 設計 alignment，per V3-QC-2）
//
// 與 feature_engineering shift(1) pattern 關係：
//   本 aggregator 的「current value 已 push 過 - shift(1) view」由 caller
//   決定 — caller 應在 push current bar 之前 query 一次 mean()，才是 leak-free。

/// 固定容量的 sliding window aggregator，O(1) 增量 mean/std。
///
/// 為什麼用 VecDeque 而非 Vec：FIFO 模式 push_back + pop_front O(1)。
/// 為什麼帶 Kahan 補償：rolling sum 浮點累積誤差會放大；對齊 indicators::kahan_sum
/// 的 V3-QC-2 精度要求。
#[derive(Debug, Clone)]
pub struct TickWindowAggregator {
    capacity: usize,
    buffer: std::collections::VecDeque<f64>,
    running_sum: f64,
    /// Kahan compensation term for running_sum.
    running_sum_c: f64,
    /// Σ x² for variance 計算。
    running_sum_sq: f64,
    running_sum_sq_c: f64,
}

impl TickWindowAggregator {
    /// 新建 capacity 固定的 aggregator。
    /// capacity = 0 表示 disabled（query 全回 None）。
    pub fn new(capacity: usize) -> Self {
        Self {
            capacity,
            buffer: std::collections::VecDeque::with_capacity(capacity.max(1)),
            running_sum: 0.0,
            running_sum_c: 0.0,
            running_sum_sq: 0.0,
            running_sum_sq_c: 0.0,
        }
    }

    /// 推入新值。若 buffer 已達 capacity 則 evict 最舊並返回它（O(1)）。
    pub fn push(&mut self, value: f64) -> Option<f64> {
        if self.capacity == 0 {
            return None;
        }
        // Kahan 補償加入 value 與 value²
        kahan_add(&mut self.running_sum, &mut self.running_sum_c, value);
        kahan_add(&mut self.running_sum_sq, &mut self.running_sum_sq_c, value * value);
        self.buffer.push_back(value);
        if self.buffer.len() > self.capacity {
            // 為什麼 if let Some 而非 unwrap：上面 len > capacity guard 邏輯上保證
            //   pop_front 必返 Some，但 unwrap 違反 E2 profile「unwrap 僅限不可
            //   恢復場景」guideline。if let 是等價且更 idiom 的寫法。
            if let Some(evicted) = self.buffer.pop_front() {
                kahan_add(&mut self.running_sum, &mut self.running_sum_c, -evicted);
                kahan_add(
                    &mut self.running_sum_sq,
                    &mut self.running_sum_sq_c,
                    -evicted * evicted,
                );
                return Some(evicted);
            }
        }
        None
    }

    /// 當前 mean — O(1)。
    ///
    /// 為什麼 None：未滿 capacity 不出 partial mean — fail-closed 避誤判
    /// （與 feature_engineering::shift1_rolling_mean 一致）。
    pub fn mean(&self) -> Option<f64> {
        if self.buffer.len() < self.capacity || self.capacity == 0 {
            return None;
        }
        Some(self.running_sum / self.capacity as f64)
    }

    /// 當前 population std — O(1)（ddof=0）。
    ///
    /// 公式：var = E[X²] - E[X]²
    /// 為什麼 ddof=0：對齊 feature_engineering::shift1_rolling_std + SQL stddev_pop。
    pub fn std(&self) -> Option<f64> {
        if self.buffer.len() < self.capacity || self.capacity == 0 {
            return None;
        }
        let n = self.capacity as f64;
        let mean = self.running_sum / n;
        let mean_sq = self.running_sum_sq / n;
        let var = (mean_sq - mean * mean).max(0.0); // 數值誤差可能略 < 0，clamp
        Some(var.sqrt())
    }

    pub fn size(&self) -> usize {
        self.buffer.len()
    }

    pub fn capacity(&self) -> usize {
        self.capacity
    }

    pub fn is_full(&self) -> bool {
        self.buffer.len() >= self.capacity && self.capacity > 0
    }
}

/// Kahan 補償求和。比較 sum += value：
///   y = value - c
///   t = sum + y
///   c = (t - sum) - y  ← 保留誤差項
///   sum = t
fn kahan_add(sum: &mut f64, c: &mut f64, value: f64) {
    let y = value - *c;
    let t = *sum + y;
    *c = (t - *sum) - y;
    *sum = t;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn aggregator_unfull_returns_none() {
        let mut agg = TickWindowAggregator::new(5);
        agg.push(1.0);
        agg.push(2.0);
        assert_eq!(agg.mean(), None);
        assert_eq!(agg.std(), None);
    }

    #[test]
    fn aggregator_full_returns_correct_mean() {
        let mut agg = TickWindowAggregator::new(3);
        agg.push(10.0);
        agg.push(20.0);
        agg.push(30.0);
        assert!((agg.mean().unwrap() - 20.0).abs() < 1e-10);
    }

    #[test]
    fn aggregator_evicts_oldest_on_overflow() {
        let mut agg = TickWindowAggregator::new(3);
        agg.push(1.0);
        agg.push(2.0);
        agg.push(3.0);
        // 第 4 push 應 evict 1.0
        let evicted = agg.push(4.0);
        assert_eq!(evicted, Some(1.0));
        // mean = (2+3+4)/3 = 3
        assert!((agg.mean().unwrap() - 3.0).abs() < 1e-10);
    }

    #[test]
    fn aggregator_std_ddof_zero() {
        // values = [10, 10, 10] → std = 0
        let mut agg = TickWindowAggregator::new(3);
        agg.push(10.0);
        agg.push(10.0);
        agg.push(10.0);
        assert!(agg.std().unwrap() < 1e-10);
    }

    #[test]
    fn aggregator_std_population_calculation() {
        // values = [1, 2, 3] → mean=2 var=(1+0+1)/3=0.667 std≈0.8165
        let mut agg = TickWindowAggregator::new(3);
        agg.push(1.0);
        agg.push(2.0);
        agg.push(3.0);
        let std = agg.std().unwrap();
        let expected = (2.0_f64 / 3.0_f64).sqrt();
        assert!((std - expected).abs() < 1e-10, "got {}, expected {}", std, expected);
    }

    #[test]
    fn aggregator_capacity_zero_disabled() {
        let mut agg = TickWindowAggregator::new(0);
        let evicted = agg.push(1.0);
        assert_eq!(evicted, None);
        assert_eq!(agg.mean(), None);
        assert_eq!(agg.std(), None);
    }

    #[test]
    fn aggregator_kahan_precision_under_many_pushes() {
        // 推入 100k 相同的 0.1，naive sum 會累積 1e-12 級誤差；
        // Kahan 補償應接近 ideal 0.1。
        let mut agg = TickWindowAggregator::new(1000);
        for _ in 0..100_000 {
            agg.push(0.1);
        }
        // 最後 1000 個都是 0.1 → mean 應極接近 0.1
        let mean = agg.mean().unwrap();
        assert!(
            (mean - 0.1).abs() < 1e-12,
            "Kahan compensation should keep mean very close to 0.1, got {}",
            mean
        );
    }
}
