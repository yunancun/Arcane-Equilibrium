# 2026-06-13 — L2 V140 + FTS-only pipeline activation

## 結論

`PASS / FTS-ONLY-ACTIVE / EMBED-BACKFILL-OFF`。

我已按你的指令先做 V140，再做 L2。這次沒有 CI、沒有 rebuild、沒有 restart。

## V140

- run id：`l2_manual_v140_apply_20260613T164628Z`
- log：`/tmp/openclaw/l2_manual_v140_apply_20260613T164628Z.log`
- sha256：`3ccc6dc3ebcc69e0ee80027536a6d7d3325e6adc4a00d66279a45155bab07beb`
- 結果：`vector` extension installed `0.8.1`
- `agent.agent_memory.embedding`：`vector(1024)`
- HNSW index：`agent.idx_agent_memory_embedding_hnsw`
- `_sqlx_migrations` 仍是 V139，這是預期；V140 是 manual path，不進 sqlx 鏈。

## L2

- FTS-only pipeline smoke：PASS
- pending day：2026-06-12
- 該日 `l2_calls=0`、DRAR=0，所以 smoke 是 no-op
- cursor 已推到：`2026-06-12`
- `agent.agent_memory` 仍是 99 rows，沒有新增非 seed rows
- daily cron 已安裝：每天 05:23 UTC
- crontab entry 內 `OPENCLAW_L2_MEMORY_PIPELINE=1`
- `[83]-[89]`：SUMMARY ALL PASS
- `[88]`：rows=99、last_success=2026-06-12、lag_days=1
- `[89]`：embed backfill OFF，PASS-skip
- engine PID `3607315` alive

## 邊界

仍未做：

- `bge-m3` pull
- `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1`
- embedding backfill
- B3 recall injection
- Gate-B probe
- rebuild / restart

下一步最自然是 pull/確認 `bge-m3`，然後做 embedding backfill；或者等下一個非空 L2 material day，拿第一個真蒸餾模型呼叫證據。
