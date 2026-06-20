# 2026-06-20 -- FlashDip L1 timing-relation diagnostics

PM source report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-20--flash_dip_l1_timing_relation_diagnostics.md`.

## Result

The latest read-only FlashDip L1 replay is still not actionable:

- Verdict: `L1_SHORT_EXIT_INSUFFICIENT_SAMPLE`
- Candidate events: 6
- Event windows with L1: 0
- Event windows missing L1: 6
- Dominant relation: `candidate_window_before_symbol_l1_range`
- Latest artifact SHA256: `43992d40987e61a737b109721b4f079347bddb382fa71c69631cae3a19c75afd`

This means the candidate maker windows happened before the loaded L1 range for those symbols. It is a data-timing blocker, not evidence that queue/fill realism killed the 240m short-exit hypothesis.

## Operator Read

No live/demo parameter change is justified. Keep L1 recording and the daily replay cron running. The next useful trigger is a future K6/N2/C3/nf0.5% candidate whose UTC maker window has continuous L1 coverage from the beginning of the window.

Alpha discovery after refresh remains non-actionable: `ready_for_probe=0`, `ready_for_aeg_chain=0`.

## Boundary

No restart, rebuild, strategy/risk change, DB schema/table write, Bybit private/signed/trading call, or credential/auth mutation.
