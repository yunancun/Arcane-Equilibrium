# EXIT-FEATURES-WRITER-BUG-1 audit RCA — MIT 2026-04-26

**狀態**：✅ Audit 完成（5 hypothesis 對比 + DB-verified RCA + 雙因並列 + 3 修復路徑）
**MIT 來源**：sub-agent task `a21061451c8ed4490`（PM 派 background）
**落檔人**：PM 代寫（MIT sub-agent 因 system reminder OVERRIDE 無法自寫 .md）
**採集時間**：2026-04-26 14:35 CEST（healthcheck snapshot 117 vs 80；早 ~1h 為 134 vs 97；delta 37 一致）

---

## §1 現象（DB-verified）

Healthcheck `[3] exit_features_writer` 連續 FAIL pre-existing：
- `exit_features_24h=117 vs close_fills_24h=80 (delta 37)` — writer broken
- 兩 query 同 scope `engine_mode = 'demo'` + 24h window 對齊
- delta 37 跨多時段一致

**EF rows by `exit_trigger_rule` (24h)**：
- `phys_lock_gate4_giveback`: 70（PHYS-LOCK 退場 ✅）
- `fast_track_reduce_half`: **40**（FastTrack 部分減倉，**異常**）
- `grid_close_long`: 5
- `grid_close_short`: 2
- 合計 117

**fills rows by `strategy_name` (24h)**：
- `risk_close:phys_lock_gate4_giveback`: 70 closes（all `realized_pnl != 0` ✅）
- `risk_close:fast_track_reduce_half`: 40 fills（**3 with `realized_pnl != 0` + 37 with `realized_pnl = 0`** ← 元兇）
- 其他 close 7
- 合計 close_fills with realized_pnl != 0 = 80

**delta 37 = STRKUSDT dust spiral 的 37 個 `realized_pnl = 0` fast_track 半倉 fill**

## §2 5 Hypothesis 對比

| H | 假說 | 結論 |
|---|---|---|
| H1 | builder 對無 close trade 也寫 | **REJECTED** — `build_exit_features_for_tick` 不寫 DB（只供 4-Gate 決策） |
| H2 | close_fill detection 漏 partial close | **PARTIAL** — 不是漏，是 EF writer 對 dust 部分平倉也寫 |
| H3 | retry-on-error 重複 | **REJECTED** — `ON CONFLICT (context_id, ts) DO UPDATE` 防重 + 0 collision |
| H4 | healthcheck SQL bug | **PARTIAL** — SQL 對，但隱含 1:1 假設不成立 |
| H5 | engine_mode mismatch | **REJECTED** — 兩邊都 100% 'demo' |

## §3 STRKUSDT dust spiral 完整證據（7d position lineage）

```
2026-04-23 19:30  ma_crossover entry qty=2269.1 → close 2269 (留 0.1 dust)
2026-04-24 03:08  ma_crossover entry qty=2221.5 → close 2221.5 (full)
2026-04-24 03:14  grid_trading entry qty=2224.6 → close 2224.5 (留 0.1 dust)
2026-04-24 03:17  →→→ 2-day gap (engine restart, 0 fills) →→→
2026-04-26 07:37  fast_track_reduce_half qty=0.05  notional=$0.002  pnl=0  ← spiral start
2026-04-26 07:38  fast_track_reduce_half qty=0.025                pnl=0
2026-04-26 07:39  fast_track_reduce_half qty=0.0125               pnl=0
... (37 halvings, 60s 一次, qty 從 0.05 → 7.3e-13)
2026-04-26 08:13  fast_track_reduce_half qty=7.3e-13              pnl=0  ← spiral end
```

## §4 雙因 root cause

### RCA-A 主因：FastTrack ReduceToHalf 對 dust legacy 倉位無限半倉
- **位置**：`rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs:315-340`
- **病灶**：MICRO-PROFIT-FIX-1 防護 fail-open
  ```rust
  if *entry_notional <= 0.0 { return true; }  // line 317 — legacy/restored dust 走這條
  ```
- **後果**：fast_track 每 60s 對 STRKUSDT 0.05 unit dust 半倉一次 × 37 次 → 37 個 `realized_pnl=0` fill + 37 個 EF rows
- **嚴重度**：交易層面無影響（dust qty < Bybit min order size 不可能成交），但**污染 ML training set 37 個 noise label**

### RCA-B 併發因：EF writer 對 partial reduce 也寫 row
- **位置**：`rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs:217 try_emit_exit_feature_row`
- **病灶**：`emit_close_fill` 對 fast_track ReduceToHalf 「partial reduce」也呼叫 → EF 寫入「位置仍 open 的 partial reduce」label
- **語意問題**：EF 設計為 **post-close 標籤**（給 Track P / ML training 用），partial reduce 不該寫
- **後果**：即使 RCA-A 修了，partial reduce 仍會在 EF 留 row（雖然不再 spam dust）

**修 RCA-A 解 dust spiral 問題；修 RCA-B 解 EF semantics 問題**。兩個都修才符合 healthcheck 1:1 假設。

## §5 推薦修復路徑（E1 範疇）

### 路徑 1：堵 RCA-A（治源頭，建議優先）
**檔**：`step_0_fast_track.rs:315-340`
- **A1 保守**：加 dust qty floor — 即使 `entry_notional == 0`（legacy），仍檢查 `qty * last_price < absolute_dust_threshold`（如 $0.01）→ 跳過半倉
- **A2 積極**：legacy `entry_notional == 0` 時走 dust eviction 路徑（直接 close + quarantine）
- **A3 最徹底**：重啟時對 paper_state restore 出來的 `entry_notional == 0` 倉位執行 dust eviction

### 路徑 2：堵 RCA-B（治對稱性，與路徑 1 互補）
**檔**：`pipeline_helpers.rs:217 try_emit_exit_feature_row`
- **B1**：`emit_close_fill` 內加 condition `if realized_pnl == 0 → 跳過 EF emit`
- **B2**：`try_emit_exit_feature_row` 內加 dust threshold（`qty * close_price < threshold` → skip）
- **B3 schema 層**：EF 增 column `is_full_close: BOOL`，writer 寫入時據 `realized_pnl != 0` 設值；healthcheck SQL filter `WHERE is_full_close = true`（**需 V026 migration**）

### 路徑 3：堵 Healthcheck（**不推薦單獨用**）
**檔**：`helper_scripts/db/passive_wait_healthcheck/checks_engine.py:159`
- EF count 加 `realized_net_bps != 0` filter 或 `exit_trigger_rule NOT LIKE 'fast_track%'` filter
- **問題**：遮蓋訊號，不修 root cause；其他 partial reduce 路徑落入相同陷阱
- **建議**：1+2 修完後 C 不需要

**推薦 sequence**：E1 同 commit 並修 1+2（cohesive PR），然後 healthcheck 自動回 PASS。

## §6 不確定 / 追加 audit follow-up

1. **Engine 重啟為何沒清掉 0.1 dust** — `paper_state::restore_from_db` 讀取 dust qty 但 entry_notional = 0；查 dust handling 邏輯（PA 派 E1 audit）
2. **V026 migration 必要性** — RCA-B 修法 B3 需 schema 改動 + Guard A
3. **fast_track sigma_scaled cooldown 是否 mis-firing** — 60s 等距 spiral 暗示 cooldown 沒擋下 dust 倉位（dust 無 drop 訊號 → 走 base FT_REDUCE_COOLDOWN_MS）
4. **其他 partial reduce 路徑** — grid_trading partial close / ma_crossover stop ladder 是否也呼 emit_close_fill（**E1 follow-up audit**）
5. **歷史 ML training 污染量化** — 全期 `learning.exit_features` 中 `dust spiral noise` 比例（`exit_trigger_rule = 'fast_track_reduce_half' AND realized_net_bps == -5.5`）（**ML training data hygiene wave**）
6. **MICRO-PROFIT-FIX-1 healthcheck 覆蓋** — 加 dedicated check 偵測 fast_track dust spiral 復發（G6 healthcheck wave）

## §7 Smoking gun reproducible query

```sql
SELECT
  ef.exit_trigger_rule,
  CASE WHEN f.realized_pnl != 0 THEN 'pnl_nonzero' ELSE 'pnl_zero' END AS fill_class,
  COUNT(*) AS rows
FROM learning.exit_features ef
LEFT JOIN trading.fills f ON ef.context_id = f.context_id
WHERE ef.ts > now() - interval '24 hours' AND ef.engine_mode = 'demo'
GROUP BY 1, 2 ORDER BY 1, 2;
-- 預期回：fast_track_reduce_half pnl_zero=37（即 delta）
```

## §8 PM 後續行動（Backlog ticket）

### EXIT-FEATURES-WRITER-BUG-1-FIX（P1，立即可派）
- **Owner**: E1（cohesive 1+2 修）
- **工時**: 3-5h（1+2+test）
- **完成標準**:
  - 路徑 1（A1 + A3）落地 → fast_track 不再對 dust legacy spiral
  - 路徑 2（B1 簡單版）落地 → partial reduce 不寫 EF
  - 跑 1h 觀察 [3] healthcheck 自動 PASS（delta < 26 = max(3, close_fills//3)）
  - 加 unit test 驗證 dust spiral 防護生效

### ML-TRAINING-DATA-HYGIENE-1（P2，下次 audit wave）
- **Owner**: MIT + E1
- **工時**: 1-2d
- **內容**:
  - SQL 量化全期 `learning.exit_features` 中 dust spiral noise 比例
  - 補回填 SQL 移除歷史 dust noise label（如比例 > 5%）
  - 加 healthcheck 偵測 dust spiral 復發

### PAPER-STATE-DUST-RESTORE-AUDIT（P2，PA 派 E1）
- **Owner**: PA design + E1 audit
- **工時**: 0.5-1d
- **內容**: `paper_state::restore_from_db` dust handling 邏輯 audit + 是否該 startup-time evict dust 倉位

---

**MIT 簽核**：findings sound + reproducible / 5 hypothesis 全 verified / smoking gun SQL 可復現 / 雙因並列不強行收斂

**PM 接收**：派 E1 修 1+2 cohesive PR；下次 audit wave 跑 ML training data hygiene
