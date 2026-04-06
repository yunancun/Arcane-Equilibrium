//! LinUCB core inference: ridge regression theta + UCB selection + per-arm update.
//! LinUCB 核心推理：ridge regression theta + UCB 選擇 + per-arm 更新。
//!
//! MODULE_NOTE (EN): Implements §1.3.1 of math_implementation_notes.md Entry 01.
//!   A_a = lambda*I + sum x x^T  (d x d, row-major Vec<f64>)
//!   b_a = sum r * x              (d-vector)
//!   theta_a = A_a^{-1} * b_a     (ridge solution via in-place Gaussian elimination)
//!   UCB_a(x) = theta_a^T x + alpha * sqrt(x^T A_a^{-1} x)
//!   Cold-start prior: A = lambda*I, b = 0  (theta = 0, max exploration).
//!   Self-contained linear algebra (no nalgebra dep) — small d (~16) keeps O(d^3) cheap.
//! MODULE_NOTE (中): 實作 math notes Entry 01 §1.3.1。
//!   A_a = lambda*I + sum x x^T   (d x d 行優先 Vec<f64>)
//!   b_a = sum r * x              (d 維向量)
//!   theta_a = A_a^{-1} * b_a     (ridge 解，原地高斯消去)
//!   UCB_a(x) = theta_a^T x + alpha * sqrt(x^T A_a^{-1} x)
//!   Cold-start prior：A = lambda*I, b = 0（theta = 0，最大探索）。
//!   自帶線性代數（不依賴 nalgebra），d 小（~16）時 O(d^3) 成本可忽略。

/// LinUCB hyperparameters / LinUCB 超參數
#[derive(Debug, Clone, Copy)]
pub struct LinUcbConfig {
    /// Context feature dimension d / 上下文特徵維度 d
    pub context_dim: usize,
    /// UCB exploration coefficient (Li et al. 2010 default 1.0) / 探索係數
    pub alpha: f64,
    /// Ridge prior strength (default 1.0) / Ridge 先驗強度
    pub lambda: f64,
}

impl Default for LinUcbConfig {
    fn default() -> Self {
        Self {
            context_dim: 16,
            alpha: 1.0,
            lambda: 1.0,
        }
    }
}

/// Per-arm sufficient statistics held in memory.
/// 每個 arm 的充分統計量（in-memory）。
#[derive(Debug, Clone)]
pub struct ArmState {
    pub arm_id: String,
    /// Row-major d*d design matrix A = lambda*I + sum x x^T
    /// 行優先 d*d 設計矩陣 A
    pub a_matrix: Vec<f64>,
    /// d-vector b = sum r * x
    /// d 維向量 b
    pub b_vector: Vec<f64>,
    /// Number of times this arm has been pulled / 該 arm 被選次數
    pub n_pulls: i64,
}

impl ArmState {
    /// Cold-start arm with identity prior: A = lambda*I, b = 0.
    /// Cold-start arm，identity 先驗：A = lambda*I, b = 0。
    pub fn cold_start(arm_id: impl Into<String>, dim: usize, lambda: f64) -> Self {
        let mut a = vec![0.0; dim * dim];
        for i in 0..dim {
            a[i * dim + i] = lambda;
        }
        Self {
            arm_id: arm_id.into(),
            a_matrix: a,
            b_vector: vec![0.0; dim],
            n_pulls: 0,
        }
    }
}

/// In-place Gaussian elimination solving A * x = rhs (consumes a clone of A).
/// Returns None if matrix is singular within tolerance.
/// 原地高斯消去解 A * x = rhs（消耗 A 的副本）。
/// 矩陣奇異時返回 None。
fn solve_linear_system(a: &[f64], rhs: &[f64], dim: usize) -> Option<Vec<f64>> {
    if a.len() != dim * dim || rhs.len() != dim {
        return None;
    }
    // Augmented matrix [A | rhs] / 增廣矩陣
    let mut m = vec![0.0_f64; dim * (dim + 1)];
    for i in 0..dim {
        for j in 0..dim {
            m[i * (dim + 1) + j] = a[i * dim + j];
        }
        m[i * (dim + 1) + dim] = rhs[i];
    }

    // Forward elimination with partial pivoting / 部分主元高斯消去
    for col in 0..dim {
        // Find pivot row / 尋找主元
        let mut pivot = col;
        let mut max_abs = m[col * (dim + 1) + col].abs();
        for r in (col + 1)..dim {
            let v = m[r * (dim + 1) + col].abs();
            if v > max_abs {
                max_abs = v;
                pivot = r;
            }
        }
        if max_abs < 1e-12 {
            return None; // singular / 奇異
        }
        if pivot != col {
            for k in 0..(dim + 1) {
                m.swap(col * (dim + 1) + k, pivot * (dim + 1) + k);
            }
        }
        // Eliminate below / 向下消元
        for r in (col + 1)..dim {
            let factor = m[r * (dim + 1) + col] / m[col * (dim + 1) + col];
            for k in col..(dim + 1) {
                m[r * (dim + 1) + k] -= factor * m[col * (dim + 1) + k];
            }
        }
    }

    // Back substitution / 回代
    let mut x = vec![0.0_f64; dim];
    for i in (0..dim).rev() {
        let mut s = m[i * (dim + 1) + dim];
        for j in (i + 1)..dim {
            s -= m[i * (dim + 1) + j] * x[j];
        }
        x[i] = s / m[i * (dim + 1) + i];
    }
    Some(x)
}

/// Compute ridge regression solution theta = A^{-1} b.
/// 計算 ridge regression 解 theta = A^{-1} b。
pub fn compute_theta(state: &ArmState, dim: usize) -> Vec<f64> {
    solve_linear_system(&state.a_matrix, &state.b_vector, dim).unwrap_or_else(|| vec![0.0; dim])
}

/// Compute UCB score for context x: theta^T x + alpha * sqrt(x^T A^{-1} x).
/// 計算 context x 的 UCB 分數：theta^T x + alpha * sqrt(x^T A^{-1} x)。
pub fn compute_ucb(state: &ArmState, x: &[f64], alpha: f64, dim: usize) -> f64 {
    if x.len() != dim {
        return f64::NEG_INFINITY;
    }
    let theta = compute_theta(state, dim);
    let mean: f64 = theta.iter().zip(x.iter()).map(|(t, xi)| t * xi).sum();

    // Solve A * u = x  =>  x^T A^{-1} x = x^T u
    // 解 A * u = x  =>  x^T A^{-1} x = x^T u
    let u = solve_linear_system(&state.a_matrix, x, dim).unwrap_or_else(|| vec![0.0; dim]);
    let var: f64 = x.iter().zip(u.iter()).map(|(xi, ui)| xi * ui).sum();
    let bonus = alpha * var.max(0.0).sqrt();
    mean + bonus
}

/// Pick the arm with maximum UCB. None if arms is empty.
/// 選 UCB 最大的 arm。空時返回 None。
pub fn select_arm<'a>(
    arms: &'a [ArmState],
    x: &[f64],
    cfg: &LinUcbConfig,
) -> Option<&'a ArmState> {
    if arms.is_empty() {
        return None;
    }
    let mut best_idx = 0;
    let mut best_ucb = compute_ucb(&arms[0], x, cfg.alpha, cfg.context_dim);
    for (i, arm) in arms.iter().enumerate().skip(1) {
        let u = compute_ucb(arm, x, cfg.alpha, cfg.context_dim);
        if u > best_ucb {
            best_ucb = u;
            best_idx = i;
        }
    }
    Some(&arms[best_idx])
}

/// Update arm state with observation (x, reward): A += x x^T, b += r * x, n_pulls++.
/// 用觀測 (x, reward) 更新 arm 狀態：A += x x^T, b += r * x, n_pulls++。
pub fn update(state: &mut ArmState, x: &[f64], reward: f64) {
    let dim = state.b_vector.len();
    if x.len() != dim {
        return;
    }
    for i in 0..dim {
        for j in 0..dim {
            state.a_matrix[i * dim + j] += x[i] * x[j];
        }
        state.b_vector[i] += reward * x[i];
    }
    state.n_pulls += 1;
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg(d: usize) -> LinUcbConfig {
        LinUcbConfig {
            context_dim: d,
            alpha: 1.0,
            lambda: 1.0,
        }
    }

    #[test]
    fn test_compute_theta_identity_prior_returns_zero() {
        // A = I, b = 0  =>  theta = 0
        let s = ArmState::cold_start("a", 4, 1.0);
        let theta = compute_theta(&s, 4);
        for v in theta {
            assert!(v.abs() < 1e-12);
        }
    }

    #[test]
    fn test_compute_ucb_zero_pulls_explores_high() {
        // Cold start arm with non-zero context should yield positive UCB (pure exploration bonus).
        let s = ArmState::cold_start("a", 3, 1.0);
        let x = vec![1.0, 1.0, 1.0];
        let u = compute_ucb(&s, &x, 1.0, 3);
        // theta=0 so mean=0; bonus = sqrt(x^T I^{-1} x) = sqrt(3)
        assert!((u - 3.0_f64.sqrt()).abs() < 1e-9);
    }

    #[test]
    fn test_compute_ucb_positive_reward_increases_theta() {
        let mut s = ArmState::cold_start("a", 2, 1.0);
        let x = vec![1.0, 0.0];
        // Pull many times with positive reward / 多次正回報
        for _ in 0..50 {
            update(&mut s, &x, 1.0);
        }
        let theta = compute_theta(&s, 2);
        assert!(theta[0] > 0.5, "theta[0]={}", theta[0]);
        assert!(theta[1].abs() < 1e-9);
    }

    #[test]
    fn test_update_increases_n_pulls() {
        let mut s = ArmState::cold_start("a", 2, 1.0);
        update(&mut s, &[1.0, 0.0], 0.5);
        update(&mut s, &[0.0, 1.0], 0.5);
        assert_eq!(s.n_pulls, 2);
    }

    #[test]
    fn test_update_a_matrix_outer_product() {
        let mut s = ArmState::cold_start("a", 2, 1.0);
        // Initial A = I; after update with x=(1,2), r=0:
        // A = I + [[1,2],[2,4]] = [[2,2],[2,5]]
        update(&mut s, &[1.0, 2.0], 0.0);
        assert!((s.a_matrix[0] - 2.0).abs() < 1e-12);
        assert!((s.a_matrix[1] - 2.0).abs() < 1e-12);
        assert!((s.a_matrix[2] - 2.0).abs() < 1e-12);
        assert!((s.a_matrix[3] - 5.0).abs() < 1e-12);
    }

    #[test]
    fn test_update_b_vector_reward_scaled() {
        let mut s = ArmState::cold_start("a", 3, 1.0);
        update(&mut s, &[1.0, 2.0, 3.0], 2.0);
        assert!((s.b_vector[0] - 2.0).abs() < 1e-12);
        assert!((s.b_vector[1] - 4.0).abs() < 1e-12);
        assert!((s.b_vector[2] - 6.0).abs() < 1e-12);
    }

    #[test]
    fn test_select_arm_picks_max_ucb() {
        // Arm A learned positive reward in direction (1,0); Arm B cold start.
        // For x=(1,0), arm A should win on the mean term once exploration is small enough.
        let mut a = ArmState::cold_start("A", 2, 1.0);
        for _ in 0..200 {
            update(&mut a, &[1.0, 0.0], 1.0);
        }
        let b = ArmState::cold_start("B", 2, 1.0);
        let arms = vec![a, b];
        let x = vec![1.0, 0.0];
        // Use small alpha so mean dominates / 用小 alpha 讓 mean 佔優
        let cfg_small = LinUcbConfig {
            context_dim: 2,
            alpha: 0.1,
            lambda: 1.0,
        };
        let chosen = select_arm(&arms, &x, &cfg_small).unwrap();
        assert_eq!(chosen.arm_id, "A");
    }

    #[test]
    fn test_select_arm_empty_returns_none() {
        let arms: Vec<ArmState> = vec![];
        let chosen = select_arm(&arms, &[1.0, 0.0], &cfg(2));
        assert!(chosen.is_none());
    }
}
