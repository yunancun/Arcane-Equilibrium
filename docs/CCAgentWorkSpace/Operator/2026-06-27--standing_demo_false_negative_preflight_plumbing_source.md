# Operator Note - Standing Demo False-Negative Preflight Source

Status: `DONE_WITH_CONCERNS`

Source now lets false-negative review/preflight consume a structured `standing_demo_operator_authorization_v1` envelope and fail closed for absent/invalid/stale/live/mainnet/scope-mismatched inputs. A local smoke reached preflight ready through `standing_demo_authorization`, while bounded auth stayed review-only with no emitted auth object and active probe/order authority false/false.

Important correction: cron no longer auto-switches bounded auth to `authorize` just because a standing JSON path exists. Runtime remains unsynced at `69f6c4b2...`; next blocker is E3-reviewed runtime source/expected-head sync.

No runtime sync, service/env/crontab mutation, PG/Bybit/order action, Cost Gate lowering, active authority, or profit proof occurred.

Full report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-27--standing_demo_false_negative_preflight_plumbing_source.md`
