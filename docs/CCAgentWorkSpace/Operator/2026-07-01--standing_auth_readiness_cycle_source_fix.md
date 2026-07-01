# Standing Auth Readiness Cycle Source Fix

Source checkpoint completed for the expired standing Demo envelope blocker.

The refresh guardrail now has an explicit `--allow-expired-standing-auth-readiness-only` path so it can refresh an expired standing auth without requiring that same expired auth to already be READY. This exception is narrow: it only accepts the single blocker `standing_authorization:standing_auth_expired`; plan, credential, connector, engine, candidate, and authority blockers still fail closed.

No runtime envelope was refreshed in this checkpoint. Next step is E3-reviewed runtime refresh scope: fresh Demo equity read, readiness, source-only guardrail preview, exact materialization only if READY, then validator/readiness recheck. No quote, lease, order, private endpoint, Cost Gate change, live/mainnet, fill/PnL, or proof occurred.
