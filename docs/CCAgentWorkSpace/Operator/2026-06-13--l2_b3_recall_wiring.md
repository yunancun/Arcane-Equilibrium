# 2026-06-13 — L2 B3 recall wiring

## 結論

B3 recall 已完成 source wiring，但預設仍關閉。

- 主線 `layer2_engine` 已接。
- 客座線 `ml_advisory` 已接。
- `shadow` 模式只寫 D3 metadata，不改模型 prompt。
- `1` 模式才把 recalled memory 注入 prompt。

## 旗標

```text
OPENCLAW_L2_MEMORY_RECALL=0       # default off
OPENCLAW_L2_MEMORY_RECALL=shadow  # ledger-only audit
OPENCLAW_L2_MEMORY_RECALL=1       # active prompt injection
```

## 驗證

Focused regression:

```text
92 passed
```

## 邊界

沒有 CI、沒有 deploy、沒有 rebuild/restart、沒有 DB/cron 變更，也沒有持久化開啟 runtime flag。Linux engine PID 仍是 `3607315`。

下一個低風險 runtime 步驟是之後在 operator-approved restart/deploy 後開 `OPENCLAW_L2_MEMORY_RECALL=shadow`，只驗 D3 `memory_recall_shadow` evidence；active `1` 等 shadow evidence 後再開。
