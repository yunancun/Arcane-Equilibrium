# GUI Active Supplier Runtime Rebuild/Restart

## Status

`DONE_WITH_CONCERNS`

This checkpoint deployed the GUI/Rust RiskConfig active bounded-probe supplier source into the running Demo engine binary. It is runtime hygiene and enablement-readiness work only; it is not order admission, execution evidence, fill evidence, PnL evidence, or profit proof.

Operator correction remains binding: GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not a fixed `10 USDT` cap. GUI `Max Single Position=25%` is `position_size_max_pct=25.0` and resolves from accepted Demo equity.

## Runtime Actions

- Host: `trade-core`
- Repo: `/home/ncyu/BybitOpenClaw/srv`
- Operational runtime head: `e8b5c77b171547f0660765cd6e4a9c77f391d70a`
- Docs-only sync before deploy:
  - `b3a71ccd040e8b720eb8beba8d8c6d23d6777667 -> e8b5c77b171547f0660765cd6e4a9c77f391d70a`
  - crontab expected-head full-SHA counts: old `11 -> 0`, new `0 -> 11`
  - manifest: `/tmp/openclaw/rt_sync_docs_head_before_gui_supplier_restart_20260627T115945Z/runtime_docs_head_sync_manifest.json`
  - sha: `883fbc48a2a1e41dc63895f2bcb9109c31e31193463fd9548816f42539948dd3`
- Deploy command:
  - `OPENCLAW_DATA_DIR=/tmp/openclaw bash helper_scripts/build_then_restart_atomic.sh`
- Deploy result:
  - pre-build binary sha: `826a2fe8cfb580c371cf3cd8d74b6de80651ba15a16981e4d4e47168f1ebfb9a`
  - post-build/running binary sha: `fc60b4f212c19ae0b7124b17f39af8bb4f5e993dfd652818168bb9aa373d7900`
  - engine PID: `3795702 -> 3944810`
  - `/proc/3944810/exe` sha equals on-disk release binary sha
  - API unit `openclaw-trading-api.service`: active/running, MainPID `3727506`
  - watchdog unit `openclaw-watchdog.service`: active/running, MainPID `1538268`

## Evidence

- Runtime deploy manifest: `/tmp/openclaw/gui_active_supplier_runtime_rebuild_restart_20260627T120557Z/runtime_deploy_manifest.json`
  - sha `f12a3a85542c5a587a4d1f42a27b7010c1e2e93dc6b651628225527a0c4596cf`
  - status `RUNTIME_REBUILD_RESTART_DONE_WITH_CONCERNS_NO_ORDER`
- Post-restart governance snapshot: `/tmp/openclaw/gui_active_supplier_runtime_rebuild_restart_20260627T120557Z/runtime_governance_snapshot.json`
  - sha `cc19b799582950856ad83d201937b0ca8c95c84931a3d68504dc30066185d965`
  - status `RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY`
  - Guardian `NORMAL`
  - position-size multiplier `1.0`
  - `lease_live_count=0`
  - `lease_count=0`
- Session state: `/tmp/openclaw/session_loop_state_20260627T1206Z_gui_active_supplier_runtime_rebuild_restart/session_loop_state.json`
  - sha `e43de28e7512c134f9da223f574327bbd300563ae58830b107de0b6fe6f36130`
  - status `DONE_WITH_CONCERNS`
- Runtime env posture:
  - `OPENCLAW_ALLOW_MAINNET=0`
  - `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=` blank
  - `OPENCLAW_DEMO_LEARNING_LANE_WRITER=` blank
  - `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=` blank
- Log-tail check:
  - tail artifact: `/tmp/openclaw/gui_active_supplier_runtime_rebuild_restart_20260627T120557Z/engine_log_tail_400.txt`
  - sha `dc566b03cc3c7151233c0746284d96283eb1ac1ee52f9df7ef7c698d91dad12a`
  - attention matches artifact: `/tmp/openclaw/gui_active_supplier_runtime_rebuild_restart_20260627T120557Z/engine_log_tail_400_attention_matches.txt`
  - sha `168d073d4b6cc556f13d8c3fec2d33304b32fbb5c7c8f9304bb03aeb31a46b88`
  - only attention match: CryptoPanic provider fetch warning because `CRYPTOPANIC_API_KEY` is not set

## Boundary

No order/cancel/modify was submitted. No Decision Lease was acquired or released in this checkpoint. No Bybit private/order call was made. No PG query/write was performed. No writer/adapter was enabled. No Cost Gate lowering, risk expansion, live/mainnet authority, execution, fill, PnL, or profit proof was produced.

The v641 docs commit may advance `origin/main` beyond the operational runtime head. Treat that as documentation drift only unless a later source-bearing commit or runtime binary mismatch appears.

## Next Action

Proceed to E3/BB enablement review only. Before any Demo order-capable action, revalidate in the same window:

- active bounded Demo Decision Lease
- Guardian `NORMAL` and Rust authority
- fresh actual BBO and exact order shape
- GUI-derived cap lineage from Rust RiskConfig plus accepted Demo equity
- clean book / pending-order reconciliation
- auditability and reconstructability
- no Cost Gate lowering, risk expansion, live/mainnet, or proof contamination
