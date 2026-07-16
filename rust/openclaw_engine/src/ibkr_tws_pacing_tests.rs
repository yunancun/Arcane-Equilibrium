//! W3-S3 pacing governor 測試（拆檔;`ibkr_tws_pacing.rs` 主體 + 測試分檔,同 session 範式）。
//! 全注入時鐘（`now_ms`）;零 socket / 零 wall-clock / 零硬編日期。**參數有效性測試**:每個
//! config 欄改動 → 行為可觀測變化（禁假功能）。

use super::*;

// ---------------------------------------------------------------------------
// 測試輔助
// ---------------------------------------------------------------------------

/// 小配置:lines=4 → rate=2 msg/s（burst 2, queue cap=4）。令佇列/超限測試迴圈小而清晰。
/// **注**:rate=2 → 500ms/token,恰等 default queue_timeout=500ms;需「逾時前補足 token」的
/// refill/FIFO 測試改用 `mid_cfg`（rate=10 → 100ms/token < 500ms）避開邊界重疊。
fn small_cfg() -> PacingConfig {
    PacingConfig {
        market_data_lines: 4,
        ..PacingConfig::default()
    }
}

/// 中配置:lines=20 → rate=10 msg/s（burst 10;100ms/token < queue_timeout 500ms）。供需驗
/// 「逾時前 token 補足即放行」的排隊測試,避開 rate=2 的 500ms==timeout 邊界重疊。
fn mid_cfg() -> PacingConfig {
    PacingConfig {
        market_data_lines: 20,
        ..PacingConfig::default()
    }
}

fn gov(cfg: PacingConfig) -> PacingGovernor {
    PacingGovernor::new(cfg, 0)
}

fn hist_req(bid_ask: bool, identical: u64, triple: u64) -> HistoricalRequest {
    HistoricalRequest {
        bid_ask,
        identical_key: identical,
        contract_exchange_ticktype: triple,
    }
}

fn is_admitted(o: &SubmitOutcome) -> bool {
    matches!(o, SubmitOutcome::Admitted(_))
}

// ===========================================================================
// (c) 主 token bucket:refill / burst / cap / 參數有效性
// ===========================================================================

#[test]
fn main_bucket_starts_full_allows_full_burst() {
    // lines=100 → rate=50 → burst 50。now=0 連送 50 → 全 Admitted;第 51 → 桶空 → 入佇列。
    let mut g = gov(PacingConfig::default());
    for i in 0..50 {
        assert!(
            is_admitted(&g.submit(OutboundClass::MarketData, 0)),
            "第 {i} 筆應即時放行（burst 1 秒額度）"
        );
    }
    assert!(
        matches!(
            g.submit(OutboundClass::MarketData, 0),
            SubmitOutcome::Queued(_)
        ),
        "第 51 筆桶空 → 有界排隊"
    );
}

#[test]
fn control_class_routes_through_main_bucket() {
    // S4:握手 control（START_API / 初次 reqCurrentTime）與 Heartbeat/MarketData 同走主 bucket
    // （單一出口不變量:所有 framed 訊息含握手 control 過 governor,回 Admitted 帶單一出口 grant）。
    let mut g = gov(PacingConfig::default());
    assert!(
        is_admitted(&g.submit(OutboundClass::Control, 0)),
        "Control（握手出站）滿桶應即時放行且鑄 grant"
    );
    assert_eq!(g.observe().admitted, 1, "Control 放行計入單一出口");
}

#[test]
fn main_bucket_refills_over_time() {
    // rate=10 → 每 100ms 補 1 token（100ms < queue_timeout 500ms,避開逾時邊界）。
    let mut g = gov(mid_cfg());
    for _ in 0..10 {
        assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    }
    // 桶空 → 入佇列。
    let t = match g.submit(OutboundClass::MarketData, 0) {
        SubmitOutcome::Queued(t) => t,
        _ => panic!("桶空應入佇列"),
    };
    // now=99 < 100ms（未補足一 token）且 < 500ms（未逾時）→ 佇列不動。
    assert!(g.poll(99).is_empty(), "99ms 未補足一 token → 佇列不動");
    // now=100 → 補 1 token（仍 < 500ms 逾時）→ 放行該票。
    let res = g.poll(100);
    assert_eq!(res.len(), 1);
    assert!(matches!(
        &res[0],
        QueueResolution::Admitted { ticket, .. } if *ticket == t
    ));
}

#[test]
fn main_bucket_refill_caps_at_burst_capacity() {
    // 排空後推進超長時間 → token 封頂 burst（rate=2 → 最多 2）,不無限累積。
    let mut g = gov(small_cfg());
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    // 推進 10s（遠超補滿所需）→ 桶封頂 2。
    // 只能再 burst 2 筆即時,第 3 筆入佇列（證明封頂,非累積 10s×2=20）。
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 10_000)));
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 10_000)));
    assert!(matches!(
        g.submit(OutboundClass::MarketData, 10_000),
        SubmitOutcome::Queued(_)
    ));
}

#[test]
fn market_data_lines_config_changes_rate() {
    // 參數有效性:lines=100 → burst 50;lines=20 → burst 10。改 config → 速率可觀測變化。
    let mut g100 = gov(PacingConfig {
        market_data_lines: 100,
        ..PacingConfig::default()
    });
    let mut admitted100 = 0;
    for _ in 0..60 {
        if is_admitted(&g100.submit(OutboundClass::MarketData, 0)) {
            admitted100 += 1;
        }
    }
    assert_eq!(admitted100, 50, "lines=100 → burst 50");

    let mut g20 = gov(PacingConfig {
        market_data_lines: 20,
        ..PacingConfig::default()
    });
    let mut admitted20 = 0;
    for _ in 0..60 {
        if is_admitted(&g20.submit(OutboundClass::MarketData, 0)) {
            admitted20 += 1;
        }
    }
    assert_eq!(admitted20, 10, "lines=20 → burst 10（參數真實生效）");
}

#[test]
fn tiny_lines_config_clamps_rate_to_one() {
    // lines=1 → rate=(1/2).max(1)=1（避免零速率 footgun）。burst 1。
    let mut g = gov(PacingConfig {
        market_data_lines: 1,
        ..PacingConfig::default()
    });
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    assert!(matches!(
        g.submit(OutboundClass::MarketData, 0),
        SubmitOutcome::Queued(_)
    ));
}

// ===========================================================================
// order-verb 直拒(超限不排隊) + 佇列滿即拒 + 有界性
// ===========================================================================

#[test]
fn order_verb_admitted_when_budget_available() {
    // 有 token 時 order-verb 正常放行(非一律拒)。
    let mut g = gov(small_cfg());
    assert!(is_admitted(&g.submit(OutboundClass::OrderVerb, 0)));
}

#[test]
fn order_verb_over_limit_rejects_without_queue() {
    // 排空 bucket 後 order-verb 超限 → 直拒(OrderVerbNoBudget),**佇列不增**(訂單延遲=語義謊言)。
    let mut g = gov(small_cfg());
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    // 桶空。order-verb → 直拒不排隊。
    assert!(matches!(
        g.submit(OutboundClass::OrderVerb, 0),
        SubmitOutcome::Rejected(PacingReject::OrderVerbNoBudget)
    ));
    assert_eq!(g.observe().queue_depth, 0, "order-verb 超限不得排隊");
    assert_eq!(g.observe().rejected_order_verb, 1);
}

#[test]
fn bounded_queue_full_rejects_and_is_bounded() {
    // rate=2 → burst 2, queue cap=4。排 2 + 佇 4 = 上限;第 5 個排隊項 → QueueFull(有界)。
    let mut g = gov(small_cfg());
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    for i in 0..4 {
        assert!(
            matches!(
                g.submit(OutboundClass::MarketData, 0),
                SubmitOutcome::Queued(_)
            ),
            "第 {i} 個排隊項應入佇列(cap=4)"
        );
    }
    assert_eq!(g.observe().queue_depth, 4, "佇列滿至 cap");
    // 第 5 個 → 拒(禁無界排隊,OOM 教訓)。
    assert!(matches!(
        g.submit(OutboundClass::MarketData, 0),
        SubmitOutcome::Rejected(PacingReject::QueueFull)
    ));
    assert_eq!(g.observe().queue_depth, 4, "拒後佇列仍 cap,未增長");
    assert_eq!(g.observe().rejected_queue_full, 1);
}

// ===========================================================================
// 有界排隊:逾時拒 + token 補足放行 + queue_timeout 參數有效性
// ===========================================================================

#[test]
fn queued_item_times_out_after_queue_timeout() {
    // 排空 bucket → 入佇列 → 推進 ≥ queue_timeout(500ms) → poll 逐出為 TimedOut(拒,非 drop)。
    // 逾時優先:即使此刻 token 已補足(500ms×rate),仍拒陳舊請求。
    let mut g = gov(small_cfg());
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    let t = match g.submit(OutboundClass::MarketData, 0) {
        SubmitOutcome::Queued(t) => t,
        _ => panic!("應入佇列"),
    };
    let res = g.poll(500); // 500 >= queue_timeout 500 → 逾時
    assert_eq!(res.len(), 1);
    assert!(matches!(
        &res[0],
        QueueResolution::TimedOut { ticket } if *ticket == t
    ));
    assert_eq!(g.observe().rejected_timeout, 1);
    assert_eq!(g.observe().queue_depth, 0);
}

#[test]
fn queued_item_admitted_before_timeout_when_tokens_refill() {
    // 逾時前(now < queue_timeout)且 token 補足 → poll 放行(非逾時拒)。
    let mut g = gov(mid_cfg()); // rate=10 → 100ms/token, queue_timeout 500ms
    for _ in 0..10 {
        assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    }
    let t = match g.submit(OutboundClass::MarketData, 0) {
        SubmitOutcome::Queued(t) => t,
        _ => panic!("應入佇列"),
    };
    // now=100 < 500 逾時,補 1 token → 放行(非逾時)。
    let res = g.poll(100);
    assert_eq!(res.len(), 1);
    assert!(matches!(
        &res[0],
        QueueResolution::Admitted { ticket, .. } if *ticket == t
    ));
}

#[test]
fn queue_timeout_config_effective() {
    // 參數有效性:queue_timeout=200ms → 200ms 即逾時(對比 default 500ms 於同時刻尚不逾時)。
    let cfg = PacingConfig {
        market_data_lines: 4,
        queue_timeout: Duration::from_millis(200),
        ..PacingConfig::default()
    };
    let mut g = gov(cfg);
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    match g.submit(OutboundClass::MarketData, 0) {
        SubmitOutcome::Queued(_) => {}
        _ => panic!("應入佇列"),
    }
    // now=200 >= 200 逾時 → TimedOut(default 500ms 於 200 尚不逾時,故此為參數真實生效)。
    let res = g.poll(200);
    assert_eq!(res.len(), 1);
    assert!(matches!(&res[0], QueueResolution::TimedOut { .. }));
}

#[test]
fn fifo_fairness_new_item_queues_behind_when_queue_nonempty() {
    // 佇列非空時,即使桶剛補 token,新項也不搶排在前之項(FIFO)——新項入佇列。
    let mut g = gov(mid_cfg()); // rate=10 → 100ms/token
    for _ in 0..10 {
        assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    }
    let first = match g.submit(OutboundClass::MarketData, 0) {
        SubmitOutcome::Queued(t) => t,
        _ => panic!(),
    };
    // now=100 補 1 token,但直接 submit(非 poll)→ 佇列非空 → 新項入佇列(不搶)。
    let second = match g.submit(OutboundClass::MarketData, 100) {
        SubmitOutcome::Queued(t) => t,
        _ => panic!("佇列非空 → 新項入佇列(FIFO)"),
    };
    assert_ne!(first.id(), second.id());
    // poll(100) → FIFO 先放行 first(1 token,未逾時),second 留隊。
    let res = g.poll(100);
    assert_eq!(res.len(), 1);
    assert!(matches!(&res[0], QueueResolution::Admitted { ticket, .. } if *ticket == first));
    assert_eq!(g.observe().queue_depth, 1);
}

// ===========================================================================
// (d) historical limiter 四規則
// ===========================================================================

#[test]
fn historical_rule_a_60_per_600s_window() {
    let cfg = PacingConfig::default();
    let mut h = HistoricalLimiter::new(&cfg);
    // 60 筆各獨立(distinct identical + triple → 不觸 c/d),cost 1 → 剛好填滿 60。
    for i in 0..60 {
        assert!(
            h.try_admit(&hist_req(false, i, i), 0).is_ok(),
            "第 {i} 筆應在 60/600 窗內"
        );
    }
    // 第 61 筆 → 窗超限。
    assert_eq!(
        h.try_admit(&hist_req(false, 999, 999), 0),
        Err(PacingReject::HistoricalWindowExceeded)
    );
}

#[test]
fn historical_rule_b_bid_ask_costs_double() {
    let cfg = PacingConfig::default();
    let mut h = HistoricalLimiter::new(&cfg);
    // BID_ASK cost 2 → 30 筆 = 60 成本填滿;第 31 筆超限(證明×2)。
    for i in 0..30 {
        assert!(
            h.try_admit(&hist_req(true, i, i), 0).is_ok(),
            "第 {i} 筆 BID_ASK"
        );
    }
    assert_eq!(
        h.try_admit(&hist_req(true, 999, 999), 0),
        Err(PacingReject::HistoricalWindowExceeded)
    );
}

#[test]
fn historical_rule_c_identical_request_dedup_15s() {
    let cfg = PacingConfig::default();
    let mut h = HistoricalLimiter::new(&cfg);
    // 相同 identical_key（triple 亦同但只 2 筆,不觸 d）。
    assert!(h.try_admit(&hist_req(false, 7, 7), 0).is_ok());
    // 15s 內重複 → 拒。
    assert_eq!(
        h.try_admit(&hist_req(false, 7, 7), 14_999),
        Err(PacingReject::HistoricalDuplicate)
    );
    // 滿 15s 後 → 去重窗滑出,可再送。
    assert!(h.try_admit(&hist_req(false, 7, 7), 15_000).is_ok());
}

#[test]
fn historical_rule_d_same_key_six_within_2s() {
    let cfg = PacingConfig::default();
    let mut h = HistoricalLimiter::new(&cfg);
    // same triple=42,distinct identical(避免觸 c);2s 內允許 ≤5,第 6 拒。
    for i in 0..5 {
        assert!(
            h.try_admit(&hist_req(false, i, 42), (i * 100) as u64)
                .is_ok(),
            "第 {i} 筆 same-key（2s 內 ≤5）"
        );
    }
    // 第 6 筆(仍在 2s 內)→ same-key 突發拒。
    assert_eq!(
        h.try_admit(&hist_req(false, 100, 42), 500),
        Err(PacingReject::HistoricalSameKeyBurst)
    );
    // 推進超過 2s 窗 → 舊 same-key 滑出,可再送。
    assert!(h.try_admit(&hist_req(false, 101, 42), 2_500).is_ok());
}

#[test]
fn historical_rule_a_window_prunes_across_600s_bounded() {
    // E2-F5a:推進注入時鐘**跨 600s** 驗 rule-a 主窗 prune/expiry——舊條目逐出、window 不無限
    // 增長（直證 OOM 封頂:即使長時間持續請求,窗內量恆 ≤ max_cost,deque 不無界成長。現有測試
    // 只覆蓋 15s/2s 共用 prune,600s 主窗未直接測）。
    let cfg = PacingConfig::default(); // historical_window 600s, max_cost 60
    let mut h = HistoricalLimiter::new(&cfg);
    // t=0:填滿 60（distinct identical+triple 避開 c/d）。
    for i in 0..60 {
        assert!(h.try_admit(&hist_req(false, i, i), 0).is_ok());
    }
    // 仍在 600s 窗內（t=599_999 < 600_000,舊條目 ts+600_000 未 ≤ now）→ 未滑出 → 第 61 筆超限。
    assert_eq!(
        h.try_admit(&hist_req(false, 900, 900), 599_999),
        Err(PacingReject::HistoricalWindowExceeded)
    );
    // 跨 600s（t=600_000:最早條目 ts0+600_000 ≤ 600_000 → 全逐出）→ 主窗清空,可再填滿 60。
    for i in 0..60 {
        assert!(
            h.try_admit(&hist_req(false, 1000 + i, 1000 + i), 600_000)
                .is_ok(),
            "跨 600s 舊條目逐出後應可再填滿（第 {i} 筆）"
        );
    }
    // 直證有界:再多一筆仍超限（窗封頂 60,非無限累積 120）→ deque 不無界成長。
    assert_eq!(
        h.try_admit(&hist_req(false, 9999, 9999), 600_000),
        Err(PacingReject::HistoricalWindowExceeded)
    );
}

#[test]
fn historical_rules_config_thresholds_effective() {
    // 參數有效性:改 historical_max_cost=2 → 第 3 筆即超限(對比 default 60)。
    let cfg = PacingConfig {
        historical_max_cost: 2,
        ..PacingConfig::default()
    };
    let mut h = HistoricalLimiter::new(&cfg);
    assert!(h.try_admit(&hist_req(false, 0, 0), 0).is_ok());
    assert!(h.try_admit(&hist_req(false, 1, 1), 0).is_ok());
    assert_eq!(
        h.try_admit(&hist_req(false, 2, 2), 0),
        Err(PacingReject::HistoricalWindowExceeded)
    );
}

#[test]
fn historical_via_governor_consumes_main_bucket_and_rejects_on_rule() {
    // governor 整合:historical 通過四規則後仍需主 bucket;規則違反則在主 bucket 前直拒。
    let mut g = gov(PacingConfig::default());
    // 正常 historical → 放行(扣主 bucket)。
    assert!(is_admitted(
        &g.submit(OutboundClass::Historical(hist_req(false, 1, 1)), 0)
    ));
    // 相同 identical → historical 規則直拒(不進佇列)。
    assert!(matches!(
        g.submit(OutboundClass::Historical(hist_req(false, 1, 1)), 100),
        SubmitOutcome::Rejected(PacingReject::HistoricalDuplicate)
    ));
    assert_eq!(g.observe().rejected_historical, 1);
    assert_eq!(g.observe().queue_depth, 0, "historical 規則拒不排隊");
}

// ===========================================================================
// (e) subscription lines 併發配額
// ===========================================================================

#[test]
fn line_quota_acquire_release_bounded_by_config() {
    // 上限 = market_data_lines（small_cfg=4）。
    let mut g = gov(small_cfg());
    for i in 0..4 {
        assert!(g.acquire_line().is_ok(), "第 {i} 條 line 應可佔用");
    }
    assert_eq!(g.lines_in_use(), 4);
    // 第 5 條 → 配額耗盡。
    assert_eq!(g.acquire_line(), Err(PacingReject::LinesExhausted));
    assert_eq!(g.observe().rejected_lines, 1);
    // 釋放一條 → 可再佔用。
    g.release_line();
    assert_eq!(g.lines_in_use(), 3);
    assert!(g.acquire_line().is_ok());
    assert_eq!(g.lines_in_use(), 4);
}

#[test]
fn line_release_saturates_at_zero() {
    // 過度釋放不下溢(飽和減)。
    let mut g = gov(small_cfg());
    g.release_line();
    g.release_line();
    assert_eq!(g.lines_in_use(), 0);
}

// ===========================================================================
// IB error-100 strike(三次違規斷 session)
// ===========================================================================

#[test]
fn ib_pacing_strike_third_violation_drops_session() {
    let mut g = gov(PacingConfig::default()); // strike_limit=3
    assert_eq!(
        g.record_ib_pacing_violation(),
        StrikeVerdict::Recorded { count: 1 }
    );
    assert_eq!(
        g.record_ib_pacing_violation(),
        StrikeVerdict::Recorded { count: 2 }
    );
    assert_eq!(
        g.record_ib_pacing_violation(),
        StrikeVerdict::SessionMustDrop
    );
    assert_eq!(g.observe().ib_pacing_strikes, 3);
}

#[test]
fn ib_pacing_strike_limit_config_effective() {
    // 參數有效性:strike_limit=1 → 首次違規即斷。
    let cfg = PacingConfig {
        ib_pacing_strike_limit: 1,
        ..PacingConfig::default()
    };
    let mut g = gov(cfg);
    assert_eq!(
        g.record_ib_pacing_violation(),
        StrikeVerdict::SessionMustDrop
    );
}

// ===========================================================================
// 觀測(export 給 W4 health IPC 的形態)
// ===========================================================================

#[test]
fn observation_reflects_tokens_queue_and_reject_counts() {
    let mut g = gov(small_cfg()); // rate=2 → burst 2
                                  // 初始:滿桶。
    assert_eq!(g.observe().main_tokens_available, 2);
    assert_eq!(g.observe().queue_depth, 0);
    // 放行 2 → 桶空。
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    assert_eq!(g.observe().main_tokens_available, 0);
    assert_eq!(g.observe().admitted, 2);
    // 入佇列 1 → depth 1。
    match g.submit(OutboundClass::MarketData, 0) {
        SubmitOutcome::Queued(_) => {}
        _ => panic!(),
    }
    assert_eq!(g.observe().queue_depth, 1);
}

// ===========================================================================
// 單一出口:grant 由 poll 放行時鑄造(Admitted 攜 grant)
// ===========================================================================

#[test]
fn poll_admission_mints_grant_for_queued_item() {
    // 佇列項於 token 補足時取得 grant(單一出口:出站必經 governor 鑄 grant)。
    let mut g = gov(mid_cfg()); // rate=10 → 100ms/token < 500ms timeout
    for _ in 0..10 {
        assert!(is_admitted(&g.submit(OutboundClass::MarketData, 0)));
    }
    match g.submit(OutboundClass::MarketData, 0) {
        SubmitOutcome::Queued(_) => {}
        _ => panic!(),
    }
    // now=100 補 1 token(未逾時)→ Admitted 攜 grant(grant 非 Clone/非 Copy,模塊外不可構造)。
    let res = g.poll(100);
    assert!(matches!(
        &res[0],
        QueueResolution::Admitted { grant: _, .. }
    ));
}
