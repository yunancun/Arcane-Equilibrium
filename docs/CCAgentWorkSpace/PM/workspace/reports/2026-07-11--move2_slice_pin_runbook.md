# Move 2 L1 切片釘存 — 執行 runbook（deadline 2026-07-19）

**性質**：dossier `2026-07-10--move2_decision_dossier.md` FIX-4 / GO 條件 C2 的執行記錄。$0、read-only、additive；唯一寫入=本地 immutable artifact。無 order/lease/risk/schema/engine 觸碰。

## 死線算術（read-only 探測，2026-07-11 已驗）

- `market.l1_events` retention `drop_after='21 days'`（chunk-granular，每日跑）。
- `l1_events` min ts = `2026-06-20 02:18`；最早 bb_reversion entry 信號 = `2026-06-28 18:46`。
- → 06-28 episode 的 L1 於 **2026-07-19** 起蒸發。硬 not-later-than，不賭 grace。
- 伴隨表不在此崖：`trading.fills`/`orders` 365d、`signals` 90d——一併釘存以成單一可複現 artifact。

## 驗證過的錨定事實（勿再推導）

| 事實 | 值 | 來源 |
|---|---|---|
| entry signal_type literals | **OpenLong / OpenShort**（非 LONG/SHORT） | `SELECT DISTINCT signal_type` |
| strategy_name literals | `bb_reversion` / `grid_trading` | 同上 |
| bb_rev entry 信號 episodes（≥06-20，per-symbol 30min gap-dedup） | **28 episodes / 15 symbols** | gap-island SQL |
| bb_rev realized fills（≥06-20） | 18 Buy + 18 Sell（07-03→07-11；06-20→07-03 零成交=F-12） | fills group by side |
| **G8 grid close_maker 校準** | **已蒸發**：末筆 attempt `2026-06-19 20:48`（n=287 all-time）< l1_min 06-20 → 0 存活 L1 | fills close_maker_attempt |

G8 結論：L1 上下文不可救（pre-existing loss）；`maker_markout_bps` 讀數本身在 `fills`（365d）仍在。exporter manifest 記 `g8_status=unpinnable_l1_aged_out`。

## 連線 / read-only 補償控制（已驗）

- 無專用唯讀 login role（`alr_shadow`=deny；僅 superuser `trading_admin`）。**不新建 role（access-control DDL，超出範圍）**。
- 補償控制：`data_loader.connect()` → `set_session(readonly=True)` + exporter `_apply_readonly_guards` 下 `SET default_transaction_read_only=on` + `SET statement_timeout=60000`。
- **實證**（trade-core host psycopg2）：connect OK role=trading_admin；`CREATE TEMP TABLE` 被拒 `ReadOnlySqlTransaction`。superuser 寫能力被 session flag 中和。
- DSN：`OPENCLAW_DATABASE_URL` ← `/home/ncyu/BybitOpenClaw/var/openclaw/runtime_secrets/openclaw_database_url`（libpq；禁硬編 user/pass）。host psycopg2 + pyarrow 23.0.1 present。

## 執行序（E2 SAFE_TO_RUN 後才跑）

```
# 1. 送 exporter 到 trade-core（git-sync 為正途；此處 scp 單檔）
scp srv/program_code/research/microstructure/episode_slice_pin.py \
    trade-core:~/BybitOpenClaw/srv/program_code/research/microstructure/episode_slice_pin.py
# 2. durable artifact 目錄（非 /tmp）
ssh trade-core 'mkdir -p ~/BybitOpenClaw/artifacts/move2_episode_pin'
# 3. --apply 真跑（host python3，read-only session + statement_timeout）
ssh trade-core 'cd ~/BybitOpenClaw/srv && \
  export OPENCLAW_DATABASE_URL="$(cat ~/BybitOpenClaw/var/openclaw/runtime_secrets/openclaw_database_url)" && \
  python3 -m program_code.research.microstructure.episode_slice_pin \
    --apply --out ~/BybitOpenClaw/artifacts/move2_episode_pin --statement-timeout 60000'
# 4. host 上 sha256 自驗 + 凍結 0444
ssh trade-core 'cd ~/BybitOpenClaw/artifacts/move2_episode_pin/pin_* && sha256sum -c sha256sums && chmod -R 0444 . && ls -la'
# 5. 拉回 Mac + 再驗（macOS 用 shasum -a 256）
mkdir -p artifacts && scp -r trade-core:~/BybitOpenClaw/artifacts/move2_episode_pin artifacts/
cd artifacts/move2_episode_pin/pin_* && shasum -a 256 -c sha256sums
```

## 凍結錨（FIX-4）

prereg v1.1 §0.4 piece-2 harness anchor 遷移到本 artifact 的 `manifest.sha256`——凍結斷言引 sha256，不引 live query。切片在手後死線只綁數據不綁代碼：R1 完整 ITT harness 可於 07-19 後離線重放。

## Rollback

無。純 additive read-only + 本地檔寫。中止=`rm -rf` 半成品 artifact 目錄；PG/runtime 零觸碰。
