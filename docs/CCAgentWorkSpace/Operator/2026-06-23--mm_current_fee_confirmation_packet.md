# 2026-06-23 -- MM Current-Fee Confirmation Packet

Operator-facing note.

The SOXLUSDT maker cell that clears current fee is now tracked by a standalone artifact:

- `/tmp/openclaw/alpha_discovery_throughput/mm_current_fee_confirmation_latest.json`
- `/tmp/openclaw/alpha_discovery_throughput/mm_current_fee_confirmation_latest.md`

Latest Linux refresh at `2026-06-23T18:30:31Z` reports:

- status: `MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW`
- candidate: `edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only`
- net: `0.715bps`
- history positive windows: `1`
- repeated keys: `0`
- repeat/OOS confirmed: `false`
- maker execution realism: `NOT_REACHED_REPEAT_WINDOW_REQUIRED`

Read: this is a concrete Cost Gate crossing lead, not proof. Next work is independent-window accumulation/replay for the same cell, then OOS/walk-forward, then maker execution realism.

No Cost Gate lowering, probe/order authority, runtime mutation, Bybit trading call, or promotion proof was granted.
