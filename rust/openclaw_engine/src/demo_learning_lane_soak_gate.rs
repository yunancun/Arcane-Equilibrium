//! MODULE_NOTE
//! 模塊用途:soak dispatch-edge 圍欄的 envelope 生命週期閘
//! (2026-07-02 設計正本 §1.2,docs/execution_plan/
//! 2026-07-02--soak_dispatch_edge_containment_and_drift_gate_design.md)。
//! 主要類/函數:`SoakEnvelopeGate` — 30s TTL 惰性緩存 + `last_good_expires_ms`
//! 硬上界;由 step_4_5_dispatch 在 `gate.approved` 分支頂端(demo/live_demo +
//! flag=1 前提下)呼叫,決定普通 Open 是否在派單邊界被 withhold。
//! 依賴:`demo_learning_lane::soak_envelope_state`(純判定核心,與 probe
//! admission 的 `validate_operator_authorization` 共用同一 envelope 實現)、
//! `demo_learning_lane_writer::demo_learning_lane_plan_path_from_env`
//! (plan 路徑解析與 writer 同源,杜絕雙路徑漂移)。
//! 硬邊界:任何存疑狀態(不可讀/缺檔/壞 JSON/schema 錯/欄位無效)一律
//! fail-closed 照攔;解除僅兩條確定性路徑 —— envelope 可讀且已過期,或
//! now 超過 last_good_expires_ms(operator 親簽到期時刻;plan 檔事後被刪,
//! 緩存仍保證 soak 必在簽署到期時刻結束)。flag=0 的 kill switch 由呼叫端
//! `bounded_probe_soak_isolation_enabled` 前置判定,本閘不重複讀 flag。

use std::path::PathBuf;

use crate::demo_learning_lane::{soak_envelope_state, SoakEnvelopeState};

/// envelope 讀檔 TTL:僅 demo/live_demo + flag=1 + 遇 approved Open 才觸發,
/// 30s 內複用上次分類結果,避免 tick 熱路徑高頻讀盤。
const REFRESH_TTL_MS: u64 = 30_000;
/// 節流間隔:indeterminate WARN 與 withhold log 共用(低頻觀察面,60s 足夠)。
const LOG_THROTTLE_MS: u64 = 60_000;

/// soak envelope 生命週期閘。每條 pipeline 一個實例(TickPipeline 欄位,
/// 非全局 singleton),test/cold 路徑 default 即可用。
#[derive(Debug, Default)]
pub struct SoakEnvelopeGate {
    /// 惰性解析的 plan 路徑;首次使用時經
    /// `demo_learning_lane_plan_path_from_env` 解析(與 writer spawn 同源)。
    plan_path: Option<PathBuf>,
    /// 最近一次讀檔分類結果;None = 從未刷新(下次判定必觸發讀檔)。
    state: Option<SoakEnvelopeState>,
    last_refresh_ms: u64,
    /// operator 親簽的最後一個有效到期時刻。即使 plan 檔事後不可讀,
    /// now >= last_good_expires_ms 即解除 —— soak 空轉的結構性硬上界。
    last_good_expires_ms: Option<u64>,
    last_indeterminate_warn_ms: u64,
    last_withhold_log_ms: u64,
}

impl SoakEnvelopeGate {
    /// dispatch-edge 圍欄判定:soak 是否武裝(true = withhold 本筆 approved Open)。
    ///
    /// 不變量:
    /// - Active 且 now < expires → 攔;now >= expires 即時解除(即使 TTL 未到,
    ///   soak 精確結束於 operator 親簽時刻,不受 30s 緩存延遲影響)。
    /// - Expired(可讀+確定過期)→ 解除。
    /// - Indeterminate → fail-closed 照攔 + 節流 WARN;唯一例外是 last_good
    ///   硬上界已過(簽署窗口確定結束,檔案被刪/損毀也必解除)。
    pub fn should_withhold_approved_open(&mut self, now_ms: u64) -> bool {
        self.refresh_if_stale(now_ms);
        // clone 避免 state 借用與節流欄位寫入衝突;enum 極小,approved Open
        // 頻率為每日數十~數百筆,成本可忽略。
        match self.state.clone() {
            Some(SoakEnvelopeState::Active { expires_at_ms }) => now_ms < expires_at_ms,
            Some(SoakEnvelopeState::Expired) => false,
            Some(SoakEnvelopeState::Indeterminate { reason }) => {
                if let Some(expires_at_ms) = self.last_good_expires_ms {
                    if now_ms >= expires_at_ms {
                        // last_good 硬上界:簽署到期時刻已過 → 解除。
                        return false;
                    }
                }
                if now_ms.saturating_sub(self.last_indeterminate_warn_ms) >= LOG_THROTTLE_MS {
                    self.last_indeterminate_warn_ms = now_ms;
                    tracing::warn!(
                        reason = %reason,
                        "BOUNDED-PROBE-SOAK-ENVELOPE: envelope indeterminate — fail-closed, ordinary demo opens stay withheld / envelope 存疑,fail-closed 照攔普通 demo 開倉(misconfig 態,時間上界告警由 healthcheck 哨兵另補)"
                    );
                }
                true
            }
            // refresh_if_stale 必已寫入 state;防禦性 fail-closed(從未可讀語義)。
            None => true,
        }
    }

    /// withhold log 節流:TickStats 計數每筆都加,log 每 60s 至多一條。
    pub fn should_log_withhold(&mut self, now_ms: u64) -> bool {
        if now_ms.saturating_sub(self.last_withhold_log_ms) >= LOG_THROTTLE_MS {
            self.last_withhold_log_ms = now_ms;
            true
        } else {
            false
        }
    }

    fn refresh_if_stale(&mut self, now_ms: u64) {
        if self.state.is_some() && now_ms.saturating_sub(self.last_refresh_ms) < REFRESH_TTL_MS {
            return;
        }
        let plan_path = self
            .plan_path
            .get_or_insert_with(crate::demo_learning_lane_writer::demo_learning_lane_plan_path_from_env);
        let state = match std::fs::read_to_string(&*plan_path) {
            Ok(content) => soak_envelope_state(Ok(content.as_str()), now_ms),
            Err(err) => {
                let read_err = err.to_string();
                soak_envelope_state(Err(read_err.as_str()), now_ms)
            }
        };
        if let SoakEnvelopeState::Active { expires_at_ms } = state {
            // 只記「最後一個有效簽署」的到期時刻(覆寫而非取 max):operator
            // 重簽較短窗口時上界應收縮,不能被舊簽署撐大。
            self.last_good_expires_ms = Some(expires_at_ms);
        }
        self.state = Some(state);
        self.last_refresh_ms = now_ms;
    }

    /// 測試注入 plan 路徑,避免測試依賴 process-global env(test_env_lock 教訓)。
    #[cfg(test)]
    pub(crate) fn set_plan_path_for_tests(&mut self, path: PathBuf) {
        self.plan_path = Some(path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    const T0: u64 = 1_782_040_200_000;
    const HOUR_MS: u64 = 3_600_000;

    /// 構造有效 plan JSON;expires_at_ms 由測試控制(RFC3339)。
    fn plan_json_expiring_at(expires_at_utc: &str) -> String {
        format!(
            r#"{{
                "schema_version": "cost_gate_demo_learning_lane_plan_v1",
                "generated_at_utc": "2026-06-21T11:00:00+00:00",
                "status": "READY_FOR_DEMO_LEARNING_PROBE",
                "gate_status": "OPERATOR_REVIEW",
                "main_cost_gate_adjustment": "NONE",
                "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
                "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
                "operator_authorization": {{
                    "schema_version": "bounded_demo_probe_operator_authorization_v1",
                    "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
                    "authorization_id": "auth-demo-eth-sell-001",
                    "operator_id": "operator-test",
                    "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                    "expires_at_utc": "{expires_at_utc}",
                    "authority_path_readiness_status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
                    "main_cost_gate_adjustment": "NONE",
                    "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
                    "max_authorized_probe_orders": 2,
                    "probe_authority_granted": true,
                    "order_authority_granted": true,
                    "promotion_evidence": false
                }},
                "selected_probe_candidate_count": 0,
                "probe_candidates": []
            }}"#
        )
    }

    fn rfc3339(ms: u64) -> String {
        chrono::DateTime::from_timestamp_millis(ms as i64)
            .unwrap()
            .to_rfc3339()
    }

    fn gate_with_plan(dir: &TempDir, plan_json: Option<&str>) -> SoakEnvelopeGate {
        let path = dir.path().join("plan.json");
        if let Some(json) = plan_json {
            std::fs::write(&path, json).unwrap();
        }
        let mut gate = SoakEnvelopeGate::default();
        gate.set_plan_path_for_tests(path);
        gate
    }

    #[test]
    fn valid_envelope_arms_gate_and_caches_last_good() {
        let dir = TempDir::new().unwrap();
        let expires = T0 + HOUR_MS;
        let mut gate = gate_with_plan(&dir, Some(&plan_json_expiring_at(&rfc3339(expires))));
        assert!(gate.should_withhold_approved_open(T0), "有效 envelope 必武裝");
        assert_eq!(gate.last_good_expires_ms, Some(expires));
    }

    #[test]
    fn readable_expired_envelope_disarms() {
        let dir = TempDir::new().unwrap();
        let mut gate = gate_with_plan(&dir, Some(&plan_json_expiring_at(&rfc3339(T0 - HOUR_MS))));
        assert!(
            !gate.should_withhold_approved_open(T0),
            "可讀+已過期 = 確定性解除"
        );
    }

    #[test]
    fn missing_plan_file_fails_closed() {
        let dir = TempDir::new().unwrap();
        let mut gate = gate_with_plan(&dir, None);
        assert!(
            gate.should_withhold_approved_open(T0),
            "缺檔且從未可讀 → fail-closed 照攔(misconfig 態方向安全)"
        );
    }

    #[test]
    fn malformed_json_fails_closed() {
        let dir = TempDir::new().unwrap();
        let mut gate = gate_with_plan(&dir, Some("{not json"));
        assert!(gate.should_withhold_approved_open(T0), "壞 JSON → 照攔");
    }

    #[test]
    fn invalid_envelope_fields_fail_closed() {
        // promotion_evidence 缺陷:可讀但 envelope 無效 ≠ 過期,不得放行。
        let dir = TempDir::new().unwrap();
        let bad = plan_json_expiring_at(&rfc3339(T0 + HOUR_MS))
            .replace(r#""promotion_evidence": false"#, r#""promotion_evidence": true"#);
        let mut gate = gate_with_plan(&dir, Some(&bad));
        assert!(gate.should_withhold_approved_open(T0), "欄位無效 → 照攔");
    }

    #[test]
    fn last_good_cache_keeps_withholding_until_signed_expiry_then_disarms() {
        // 設計 §1.2 硬上界:plan 檔事後被刪,soak 仍必在簽署到期時刻結束。
        let dir = TempDir::new().unwrap();
        let expires = T0 + 2 * HOUR_MS;
        let path = dir.path().join("plan.json");
        std::fs::write(&path, plan_json_expiring_at(&rfc3339(expires))).unwrap();
        let mut gate = SoakEnvelopeGate::default();
        gate.set_plan_path_for_tests(path.clone());
        assert!(gate.should_withhold_approved_open(T0));

        std::fs::remove_file(&path).unwrap();
        // TTL 已過 → 重讀失敗 → Indeterminate,但仍在簽署窗口內 → 照攔。
        assert!(
            gate.should_withhold_approved_open(T0 + REFRESH_TTL_MS + 1),
            "檔案被刪但簽署窗口未到期 → fail-closed 照攔"
        );
        // 簽署到期時刻已過 → last_good 硬上界解除。
        assert!(
            !gate.should_withhold_approved_open(expires + 1),
            "last_good 超時 → 即使檔案不可讀也必解除"
        );
    }

    #[test]
    fn ttl_caches_state_then_refresh_picks_up_expired_rewrite() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("plan.json");
        std::fs::write(&path, plan_json_expiring_at(&rfc3339(T0 + 2 * HOUR_MS))).unwrap();
        let mut gate = SoakEnvelopeGate::default();
        gate.set_plan_path_for_tests(path.clone());
        assert!(gate.should_withhold_approved_open(T0));

        // 覆寫成已過期 plan:TTL 內仍用緩存(武裝),TTL 過後刷新即解除。
        std::fs::write(&path, plan_json_expiring_at(&rfc3339(T0 - HOUR_MS))).unwrap();
        assert!(
            gate.should_withhold_approved_open(T0 + 10_000),
            "30s TTL 內複用緩存,不重讀"
        );
        assert!(
            !gate.should_withhold_approved_open(T0 + REFRESH_TTL_MS + 1),
            "TTL 過後刷新讀到過期 envelope → 解除"
        );
    }

    #[test]
    fn active_cache_disarms_exactly_at_signed_expiry_within_ttl() {
        // 到期時刻落在 TTL 窗口內:不等刷新,now >= expires 即解除。
        let dir = TempDir::new().unwrap();
        let expires = T0 + 20_000;
        let mut gate = gate_with_plan(&dir, Some(&plan_json_expiring_at(&rfc3339(expires))));
        assert!(gate.should_withhold_approved_open(T0));
        assert!(
            !gate.should_withhold_approved_open(expires),
            "緩存 Active 但 now >= expires → 即時解除(不受 30s 緩存延遲影響)"
        );
    }

    #[test]
    fn stale_plan_generated_at_does_not_disarm_valid_envelope() {
        // 刻意決策(設計 §1.2):圍欄判準 = envelope 核心(抽自
        // validate_operator_authorization),不含 plan generated_at staleness。
        // stale plan 下 admission 必拒一切(probe 不可能下單),但 soak 窗口
        // 仍以 operator 親簽 expires_at 為準 —— 時間上界不受 stale 影響。
        let dir = TempDir::new().unwrap();
        let stale = plan_json_expiring_at(&rfc3339(T0 + HOUR_MS)).replace(
            r#""generated_at_utc": "2026-06-21T11:00:00+00:00""#,
            r#""generated_at_utc": "2020-01-01T00:00:00+00:00""#,
        );
        let mut gate = gate_with_plan(&dir, Some(&stale));
        assert!(
            gate.should_withhold_approved_open(T0),
            "plan stale 但 envelope 有效 → 圍欄仍武裝(admission 另行拒 probe)"
        );
    }

    #[test]
    fn withhold_log_throttles_to_one_per_interval() {
        let mut gate = SoakEnvelopeGate::default();
        assert!(gate.should_log_withhold(T0));
        assert!(!gate.should_log_withhold(T0 + 1_000));
        assert!(gate.should_log_withhold(T0 + LOG_THROTTLE_MS));
    }
}
