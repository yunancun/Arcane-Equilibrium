# Operator Note: Reviewed Public Quote Capture Packet No-Capture

Status: `DONE_WITH_CONCERNS`

PM closed `P1-AGGRESSIVE-ALPHA-REVIEWED-PUBLIC-QUOTE-CAPTURE-PACKET-NO-CAPTURE` as source/test/docs only. The new helper `helper_scripts/research/cost_gate_learning_lane/reviewed_public_quote_capture_packet.py` defines the review packet for a future AVAX public quote capture.

The packet does not call Bybit and does not authorize runtime capture. It fixes the future request envelope to public GET only:

- `/v5/market/time`
- `/v5/market/tickers?category=linear&symbol=AVAXUSDT`
- `/v5/market/instruments-info?category=linear&symbol=AVAXUSDT`

It allows only a `User-Agent` header, rejects auth/cookie/private/order paths, keeps redirect and timeout controls, requires request/response hashes and timestamps, preserves `max_fresh_bbo_age_ms=1000`, requires adapter-backed handoff before construction preview, and carries the maker-policy spread/cost skip guard.

Smoke artifact:

`/tmp/openclaw/reviewed_public_quote_capture_packet_smoke_20260626T091205Z/reviewed_public_quote_capture_packet.json`

Smoke status is `REVIEWED_PUBLIC_QUOTE_CAPTURE_PACKET_READY_NO_CAPTURE_NO_AUTHORITY`. All authority/proof answers remain false, including runtime capture allowed, public quote capture performed, network call, Bybit call, probe/order/live authority, PG query/write, order admission, Cost Gate lowering, promotion evidence, and promotion proof.

Next if continuing: `P1-AGGRESSIVE-ALPHA-PUBLIC-QUOTE-CAPTURE-RUNTIME-REVIEW`, which is exchange-facing read-only and must run through PM->E3->BB before any capture. If a real AVAX-scoped authorization delta appears first, return to `P0-BOUNDED-PROBE-AUTHORIZATION`.
