# Operator Note: Bounded Probe Shadow Placement Impact

Date: 2026-06-22
Source commit: `ff66aa25`

v417 adds a no-authority shadow replay for the v416 near-touch-or-skip placement repair.

Current Linux smoke result:

- status: `SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH`
- candidate: `ma_crossover|BTCUSDT|Sell`
- sample scope: `current_demo_order_flow_not_candidate_matched`
- reviewed orders: `6`
- shadow submit count: `6`
- shadow skip count: `0`
- candidate-matched orders: `0`
- max original best-touch gap: `1530.6074bp`
- max shadow initial touch gap: `58.2092bp`
- max gap reduction: `1522.1026bp`

Operational meaning: the near-touch repair is mechanically useful on the current Demo order-flow sample, but it is not candidate-specific alpha evidence. The sample is flash-dip Buy order flow, not `ma_crossover|BTCUSDT|Sell`.

Do not lower Cost Gate globally. The next step still requires separate operator authorization before any Rust bounded Demo authority-path patch. After that, candidate-matched fill-backed evidence must be collected before any Cost Gate review.

No cron was installed, no env was changed, no service was restarted, no PG write occurred, no Bybit trading/private call was made, and no probe/order authority or promotion proof was granted.
