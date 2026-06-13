# 2026-06-13 — L2 V140 + FTS-only pipeline activation

## Verdict

`PASS / FTS-ONLY-ACTIVE / EMBED-BACKFILL-OFF`.

After operator approval, manual V140 was applied and the L2 daily memory distill cron was activated in FTS-only mode.

## Scope

Executed:

- manual V140 apply through `helper_scripts/db/apply_manual_V140_agent_memory_vector.sh`
- V140 reflection checks
- L2 pipeline smoke with `OPENCLAW_L2_MEMORY_PIPELINE=1` and embed backfill off
- L2 daily cron install with pipeline flag on
- active `[83]-[89]` healthcheck with pipeline flag on

Not executed:

- CI
- rebuild/restart
- `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1`
- bge-m3 pull
- embedding backfill
- B3 recall injection
- Gate-B probe

## V140 Apply

Baseline:

```text
head|139|success=true
agent_memory_rows|99
vector_installed|NULL
vector_available|0.8.1
embedding_column|NULL
embedding_index|NULL
```

Run:

- run id: `l2_manual_v140_apply_20260613T164628Z`
- log: `/tmp/openclaw/l2_manual_v140_apply_20260613T164628Z.log`
- sha256: `3ccc6dc3ebcc69e0ee80027536a6d7d3325e6adc4a00d66279a45155bab07beb`
- exit: `0`

Result:

```text
vector_installed|0.8.1
embedding_format|vector(1024)
embedding_udt|vector
embedding_index|agent.idx_agent_memory_embedding_hnsw
embedding_indexdef|CREATE INDEX idx_agent_memory_embedding_hnsw ON agent.agent_memory USING hnsw (embedding vector_cosine_ops)
agent_memory_total|99
embedding_null|99
embedding_not_null|0
embedding_pending_true|99
```

`_sqlx_migrations` remains at V139 by design because V140 is the manual path and is not part of the sqlx chain.

## L2 FTS-Only Smoke

Pre-smoke:

```text
cursor: absent
day_stats: absent
l2_calls_yesterday|0
drar_yesterday|0
agent_memory_before_l2|99
```

Run:

- run id: `l2_pipeline_ftsonly_smoke_20260613T164831Z`
- stdout log: `/tmp/openclaw/l2_pipeline_ftsonly_smoke_20260613T164831Z.log`
- stdout sha256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- actual cron log: `/tmp/openclaw/logs/l2_memory_distill_cron.log`
- actual cron log sha256: `42d5a711cb0d09e20bd456a51a06ddcb1e41c4c922059b787b3f6b9b43962c34`
- cursor sha256: `2d737acaa7e1d214b148aff32791aad6d499ae90d4ab7c77f97e677a63841624`
- day stats sha256: `87e2a75ffe707a73d402e6dc4a6d0c73d4d2dfc5caf0ff3f118713db2bc25a7f`
- exit: `0`

Smoke result:

```text
cursor=None -> pending 2026-06-12
day=2026-06-12 OK
stored=0
materials_l2=0
cursor=2026-06-12
agent_memory_after_smoke|99
non_seed_rows|0
```

No model generation was needed in this smoke because the target day had no L2/DRAR materials.

## Cron Install

Run:

- run id: `l2_memory_cron_install_20260613T164901Z`
- log: `/tmp/openclaw/l2_memory_cron_install_20260613T164901Z.log`
- sha256: `730b248eef84b4110d1aaf27dc926bc889497b24936f2263e83daff0c7a461f6`
- exit: `0`

Installed crontab entry:

```text
23 5 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets OPENCLAW_L2_MEMORY_PIPELINE=1 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/l2_memory_distill_cron.sh >> /tmp/openclaw/logs/l2_memory_distill_cron.cron.log 2>&1
```

## Post-Activation Verification

Ollama status:

```text
ollama: present
models: qwen3.5:9b-q4_K_M, qwen3.5:27b-q4_K_M
bge-m3: absent
```

Healthcheck with `OPENCLAW_L2_MEMORY_PIPELINE=1`:

```text
PASS [83] alpha_wealth_family_cardinality families=0 bound=10
PASS [84] alpha_wealth_orphan_refund orphan_refunds=0
PASS [85] alpha_wealth_refund_mismatch refund_amount_mismatches=0
PASS [86] pre_reg_cross_family_dup_spec cross_family_duplicate_specs=0
PASS [87] hidden_oos_state_regression sealed_rows_with_post_insert_updates=0
PASS [88] l2_memory_pipeline_freshness rows=99 last_success=2026-06-12 lag_days=1 (warn>3)
PASS [89] l2_memory_embedding_drift SKIP (flag off): OPENCLAW_L2_MEMORY_EMBED_BACKFILL != 1
SUMMARY: ALL PASS
```

DB state:

```text
agent_memory_total|99
embedding_pending_true|99
embedding_not_null|0
embedding_meta_rows|0
```

Engine remained alive: PID `3607315`.

## Remaining Gates

- Pull/enable `bge-m3` before embedding backfill.
- Run `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1` after bge-m3 is present.
- Capture first non-empty L2 material day and verify true model-call distillation.
- B3 recall injection remains separate.
- P2p sentinel / P5 feedback-quality-GUI remain separate.
