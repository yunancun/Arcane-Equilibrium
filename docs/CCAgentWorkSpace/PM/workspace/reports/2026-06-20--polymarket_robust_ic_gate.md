# Polymarket Robust IC Gate

## 結論

Polymarket lead-lag IC path 已有 joined label，但樣本仍極低。為避免 15m cadence 下 overlapping forward returns 造成假 ready，本輪把 harness gate 升級為 v0.3：candidate 必須同時滿足 raw IC/t threshold、overlap-adjusted sample floor、以及 BH q-value 控制。

這不是 promotion proof；它是把未來「看似正 IC」轉成更難誤判的機器 gate。

## Source Change

- `helper_scripts/research/polymarket_leadlag/__init__.py`
  - `RUNNER_VERSION=polymarket_leadlag.v0.3`
  - `REPORT_SCHEMA_VERSION=polymarket.leadlag_report.v0.3`
- `helper_scripts/research/polymarket_leadlag/harness.py`
  - Adds `n_nonoverlap_timestamps`, `overlap_adjusted_sample_floor`, `overlap_warning`.
  - Adds approximate two-sided normal p-values and BH q-values across report cells.
  - `candidate_count` now counts only cells clearing raw threshold plus `max_bh_q`.
  - `preliminary_raw_candidate_count` preserves raw pass count.
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - Uses `counts.max_overlap_adjusted_ic_points` as Polymarket arm `sample_count`.
  - Preserves raw `max_ic_points`, `preliminary_raw_candidate_count`, and `max_bh_q` in raw detail.
- `helper_scripts/cron/polymarket_leadlag_ic_cron.sh`
  - Status JSONL now exposes raw/adjusted IC sample counts and raw-vs-controlled candidate counts.

## Runtime Evidence

Linux v0.3 wrapper smoke:

- Artifact: `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T124843Z.json`
- sha256: `5cd5dde22b7bfd6d31339aca739db3126982ac5b3130d23da3478b2ed56d6de5`
- runner/schema: `polymarket_leadlag.v0.3` / `polymarket.leadlag_report.v0.3`
- Snapshot timestamps: `3`
- Delta rows: `794`
- Feature points: `12`
- Joined rows: `6`
- Label joinable pairs: `6`
- `max_ic_points=1`
- `max_overlap_adjusted_ic_points=1`
- Status: `INSUFFICIENT_SAMPLE`
- Reason: `max overlap-adjusted IC points 1 below min_points 30`

Alpha discovery refresh:

- `created_at_utc=2026-06-20T12:48:54.900509+00:00`
- `polymarket_leadlag_ic.sample_count=1`
- action `RUN_READ_ONLY_CAPTURE`
- ready/probe = `0`

## Verification

- Local: `test_polymarket_leadlag.py` + `test_alpha_discovery_throughput.py` -> `27 passed`
- Local: `test_polymarket_leadlag_ic_cron_static.py` -> `9 passed`
- Local: py_compile + `bash -n` + `git diff --check` passed
- Linux: same focused suites -> `27 passed` + `9 passed`
- Linux: py_compile + `bash -n` passed

## Boundary

Artifact/report/status only. Lead-lag PG access remains read-only SELECT with `PGOPTIONS=-c default_transaction_read_only=on`.

No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/strategy mutation, and no promotion proof.

## Next Trigger

Wait for `max_overlap_adjusted_ic_points >= 30`. If candidate_count becomes positive after BH control, dispatch QC/MIT/AI-E for residualization, regime slices, autocorrelation/HAC review, and multiple-testing audit before any AEG or strategy implication.
