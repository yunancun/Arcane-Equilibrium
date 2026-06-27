# Operator Note: Current Candidate Admission After Auth Object

State transition: `BLOCKED_BY_LOSS_CONTROL`.

The timestamped AVAX bounded auth object was consumed by the no-order admission review and is now valid for the current candidate:

- auth id `standing-demo-9309f8073f60d3db`
- candidate `grid_trading|AVAXUSDT|Sell`
- max probe orders `2`
- expiry `2026-06-27T14:51:58.043996+00:00`
- GUI cap `955.24342626 USDT`

New review:

- `/tmp/openclaw/current_candidate_bounded_demo_admission_after_auth_object_20260627T0400Z/current_candidate_bounded_demo_admission_envelope_review_after_auth_object.json`
- sha `7f21a507e41b01de7e767b7bd02723e8b3e18b09f9d647e075b7195f0c3c8303`
- status `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`

Remaining blockers:

- Decision Lease
- Guardian risk gate
- Rust authority path
- fresh actual-admission BBO

No order, writer enablement, plan mutation, active runtime authority, Cost Gate change, live authority, or profit proof occurred.
