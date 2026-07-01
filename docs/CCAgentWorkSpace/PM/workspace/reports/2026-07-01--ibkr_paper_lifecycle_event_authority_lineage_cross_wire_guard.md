# IBKR Paper Lifecycle Event Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；paper lifecycle event authority / lineage hardening

## 結論

已補強 `ibkr_paper_lifecycle` 的 append-only event identity、request lineage、paper-only authority、
transition/stale-policy、denial semantics 與 fill identity coverage。這次只改 acceptance 與 source-static
guard，不改 Rust production validator、IPC method、runtime、IBKR connector、secret、DB/evidence writer、
scorecard writer 或 paper order route。

## 變更

- Rust acceptance 新增 `lifecycle_event_rejects_each_identity_and_lineage_gap_independently`。
- Rust acceptance 新增 `lifecycle_event_rejects_each_paper_authority_and_artifact_gap_independently`。
- Rust acceptance 新增 `lifecycle_event_rejects_denial_and_fill_identity_gaps_independently`。
- Acceptance 證明 lifecycle/event-log contract ids、source version、event id/sequence/time/hash、
  previous-event hash、paper-order request contract/hash、asset lane、broker、local order id、idempotency
  key、reconciliation run id gaps 可獨立產生精確 blocker。
- Acceptance 證明 ReadOnly environment、paper lifecycle transition mismatch、broker order id、allowed-event
  denial reason、stale policy missing/mismatch、raw/redacted artifact hash gaps 可獨立阻斷。
- Acceptance 明確保留 non-paper operation 的天然 aggregate 行為：必須同時命中
  `OperationNotPaperLifecycle` 與 `OperationTransitionMismatch`。
- Acceptance 證明 denied active-state event、denied event missing reason、fill execution id、commission
  report id gaps 可獨立產生精確 blocker。
- Python source-static guard 新增 event `Default` / `accepted_ack_fixture` block parsers，直接鎖住 accepted
  ack fixture 不可硬編 live/Bybit/wrong operation/denied/empty-lineage/stale-policy-missing posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/ibkr_paper_lifecycle_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_paper_lifecycle_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test ibkr_paper_lifecycle_acceptance`：`15 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 lifecycle writer、DB/evidence writer、scorecard writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
