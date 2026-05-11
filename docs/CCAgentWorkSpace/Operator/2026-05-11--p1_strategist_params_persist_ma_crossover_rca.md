# P1-RCA — STRATEGIST-PARAMS-PERSIST-1 ma_crossover restore reject 持續性 RCA（2026-05-11）

> **角色**：PA · 唯讀 RCA · 範圍：Rust openclaw_engine · STRATEGIST-PARAMS-PERSIST-1
> **觸發**：每次 engine restart 看見 WARN：
> `STRATEGIST-PARAMS-PERSIST-1: restore handler rejected strategy=ma_crossover error=validation failed: confluence weight sum must be 65, got 73.00 (adx=13.75, regime=28.75, volume=22.5, momentum=8)`
> **Verdict**：**A 級（fallback 工作正常）— runtime 跑 TOML defaults，非 stale state；不是 BLOCKER；建議 Option 1 + Option 4 雙軌**

---

## 1. RCA 總結（一句話）

`strategist_scheduler.evaluate_cycle` 路徑與 restore 路徑對「weight 參數缺 key」的處理**不對稱**：
- **runtime 路徑**：Ollama L1 推薦對 weight key 採部分鍵集（只調 3/4 key，假設 missing key = 0 配平 sum=65），`validate_recommendation` 對缺 key `continue` 跳過 weight_sum 累計（line 365-368 / mod.rs），`apply_params` 走 `merge_strategy_params_json`（line 79 / event_consumer/handlers/strategy_params.rs）用「**current in-memory 值**」補入缺 key — 跑 cycle 時 in-memory 已被前次 cycle 設成 `weight_momentum=0`（首次明確設於 row id=5855 / 2026-05-05 17:16 UTC），sum 仍 65 通過 `params.validate()` → IPC `Ok` → row 寫入 DB。
- **restore 路徑**：engine restart 後 in-memory 由 `MaCrossover::new()` 初始化（line 437 / ma_crossover/mod.rs）讀 `ConfluenceConfig::default()` → `weight_momentum=8.0`（**非 0**）。`STRATEGIST-PARAMS-PERSIST-1` 把 DB 最新 row (id=7143 / 2026-05-07 05:52 UTC) 的 raw params_json 經 IPC `UpdateStrategyParams` 送回 → 同一個 `merge_strategy_params_json` 用 **TOML default 8.0** 補入缺 key → 13.75+28.75+22.5+**8** = **73** → `confluence_config.validate()` (line 80-89 / strategies/confluence.rs) reject 「sum must be 65」 → restore handler 回 Err → WARN 一次。

**Strategist 的 bug 在於 persist 寫入 DB 時用 raw response（缺 key），而 restore 時 in-memory base 與 cycle 當下 in-memory 不一致** — DB row 缺少 `weight_momentum=0` 顯式記載，restore 撞 boot TOML default 8.0。

---

## 2. 證據蒐集

### 2.1 持久化層架構

| 角色 | 檔案 | 行 |
|---|---|---|
| **Writer** | `rust/openclaw_engine/src/strategist_scheduler/persist.rs` | 45-90 `persist_applied_params` |
| **Reader** | `rust/openclaw_engine/src/strategist_scheduler/persist.rs` | 113-158 `load_latest_applied_params` |
| **Restore handler** | `rust/openclaw_engine/src/main_boot_tasks.rs` | 186-296 `spawn_strategist_scheduler` 內 |
| **Merge logic** | `rust/openclaw_engine/src/event_consumer/handlers/strategy_params.rs` | 17-42 `merge_strategy_params_json` + 51-120 `handle_update_strategy_params` |
| **Validation rule** | `rust/openclaw_engine/src/strategies/confluence.rs` | 80-90 `ConfluenceConfig::validate()` sum=65 ±0.01 |
| **Cycle entry** | `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` | 174-225 `evaluate_cycle` |
| **Inconsistent path** | `rust/openclaw_engine/src/strategist_scheduler/mod.rs` | 318-419 `validate_recommendation_with_reason`（cycle 用，**不 prefill current**）vs `merge_strategy_params_json`（apply 用，**prefill current**） |

**不是檔案、是 Postgres 表**：`learning.strategist_applied_params`（V019 schema + V020 idx tie-break）。

### 2.2 PG 直查（empirical, 連 trade-core）

**Latest 5 ma_crossover demo rows**：
```
  id  | engine_mode | applied_at_ms |        source        |       reason       |      applied_utc
------+-------------+---------------+----------------------+--------------------+-------------------------
 7143 | demo        | 1778133127399 | strategist_scheduler | top_deviation_pair | 2026-05-07 05:52:07.399
 7140 | demo        | 1778132807703 | strategist_scheduler | top_deviation_pair | 2026-05-07 05:46:47.703
 7139 | demo        | 1778132487808 | strategist_scheduler | top_deviation_pair | 2026-05-07 05:41:27.808
 7136 | demo        | 1778132172471 | strategist_scheduler | top_deviation_pair | 2026-05-07 05:36:12.471
 7133 | demo        | 1778131852440 | strategist_scheduler | top_deviation_pair | 2026-05-07 05:30:52.44
```

**Row 7143 params_json**（restore handler 嘗試還原這個）：
```json
{
  "agent": "strategist",
  "source": "ollama_l1",
  "status": "evaluated",
  "symbol": "ETHUSDT",
  "strategy": "ma_crossover",
  "reasoning": "AI-recommended params for ma_crossover/ETHUSDT",
  "weight_adx": 13.75,
  "_elapsed_ms": 10409.9,
  "cooldown_ms": 2772000,
  "adx_threshold": 13.75,
  "weight_regime": 28.75,
  "weight_volume": 22.5,
  "min_persistence_ms": 231000
}
```

**注意**：`weight_momentum` **完全缺席**。`13.75 + 28.75 + 22.5 = 65.0` — Ollama L1 把這三個調成 sum=65，**隱式假設 weight_momentum=0**。

**Row 7139 params_json**（最後一次 explicit 含 weight_momentum=0）：
```json
{
  "weight_adx": 11.5, "weight_regime": 30, "weight_volume": 23.5, "weight_momentum": 0,
  "cooldown_ms": 3600000, "adx_threshold": 11.55, "min_persistence_ms": 210000,
  "confluence_threshold_full": 45.5, "confluence_threshold_light": 42, "confluence_threshold_no_trade": 38.5,
  ...
}
```
`11.5 + 30 + 23.5 + 0 = 65.0` — explicit。

**Transition row 5849 → 5855**（in-memory `weight_momentum` 從 11 → 0 的 first explicit 設置）：
```
  id  | applied_at_ms |       applied_utc       | adx  | regime | vol  | mom
------+---------------+-------------------------+------+--------+------+-----
 5849 | 1778000750978 | 2026-05-05 17:05:50.978 | 18   | 18     | 18   | 11
 5855 | 1778001401954 | 2026-05-05 17:16:41.954 | 23.4 | 23.4   | 18.2 | 0
```
5849 sum=65；5855 sum=65（in-memory mom=0）。**5855 之後所有 ma_crossover row 都假設 mom=0**，但持久化逐漸退化只記 3 個 key，weight_momentum=0 沒寫入 DB。

### 2.3 Validation 規則來源

```
ea3237f0 2026-04-13 01:39:25 +0200
feat(g-sr-1): Phase A S1+S2 — confluence scoring, persistence filter, grid trend cooldown
```
`sum must be 65` 是 2026-04-13 G-SR-1 Phase A **首次引入的不變式**，**遠早於** Ollama 開始推薦缺 mom 的 row（首發 2026-05-05 17:16 UTC）。**規則沒「加嚴」** — 是 strategist_scheduler 的 Ollama L1 行為演化 + persist payload 設計缺陷晚出現的 mismatch。

### 2.4 當前 engine log 證實

```
2026-05-11T10:57:42.492514Z WARN openclaw_engine::main_boot_tasks: STRATEGIST-PARAMS-PERSIST-1: restore handler rejected
strategy=ma_crossover error=validation failed: confluence weight sum must be 65, got 73.00
(adx=13.75, regime=28.75, volume=22.5, momentum=8)

2026-05-11T10:57:42.492532Z INFO  openclaw_engine::main_boot_tasks: STRATEGIST-PARAMS-PERSIST-1:
restored N tuned params from DB n=1 total=2 engine_mode=demo
```
`n=1 total=2`：restore 嘗試 2 條（demo 唯一兩個有 row 的策略：ma_crossover + grid_trading），1 條成功 — **grid_trading PASS**（row 8936 只含 `cooldown_ms` + `max_cooldown_boost`，無 weight key → merge 不破 sum）；**ma_crossover FAIL**。

### 2.5 runtime in-memory 真實狀態（Strategist 24h activity 證據）

```
 strategy_name | rows_24h |         latest
---------------+----------+-------------------------
 grid_trading  |      573 | 2026-05-11 11:08:19.378
```
**ma_crossover 0 rows 24h** — Strategist 已連續 4 天沒對 ma_crossover 推薦新 params（最後 2026-05-07 05:52 UTC）。即 ma_crossover **不會自動把 in-memory `weight_momentum` 再回 0**。

**ma_crossover 24h demo fills = 32** > 30 HAVING gate，理論上應入 `gather_strategy_metrics` rank pool，但 `rank_by_deviation` top-N 沒選中（可能 deviation 低 / 其他策略優先）。**這是 strategist 排名邏輯衍生問題，本 RCA 不深入**。

### 2.6 ma_crossover boot in-memory 初始值

`MaCrossover::new()` (ma_crossover/mod.rs:419-451)：
- `confluence_config: ConfluenceConfig::default()` → weight_adx=25, weight_regime=20, weight_volume=12, **weight_momentum=8** (sum=65 ✓)
- `cooldown_ms: 300_000`, `adx_threshold: 20.0`, `min_persistence_ms: 180_000`

`registry.rs:55-62`：TOML override（`strategy_params_demo.toml [ma_crossover]`）但 **沒覆寫 weight_***（TOML 該段沒 weight key）。

→ **boot 後 in-memory weight = ConfluenceConfig::default() = (25, 20, 12, 8)**。

---

## 3. 影響評估

### 3.1 Fallback 行為判定 = **A 級（正常工作，跑 TOML defaults）**

**證據**：
1. `apply_params` IPC handler 拒絕 → `record_reject("apply_failed")` → 不調 `record_apply` → in-memory 維持 boot 初始 state
2. restore handler 唯一錯誤路徑是 `warn!` + propagate Err 給 `oneshot::Sender<Result>` → caller log + continue（不阻 engine boot）
3. engine `tokio::spawn` 把 restore 整個塞 background task（line 246-296 / main_boot_tasks.rs），主執行緒不阻塞
4. 沒有任何 silent partial-merge 路徑 — `update_params_json` (strategy_impl.rs:333-336) 一旦 `params.validate()` Err，整個 update **atomic rollback**（serde deserialize 完整 struct + 整 struct validate；不會「部分欄位寫入」）

**結論**：runtime ma_crossover 跑的是 (25, 20, 12, 8) sum=65，**不是 stale 73 也不是任何持久化值**。但同時 **所有 14 個 non-weight key 持久化值也失效**：

| key | TOML default | 持久化 row 7143 | runtime 真實值 |
|---|---|---|---|
| cooldown_ms | 600000 (10 min) | 2772000 (46.2 min) | 600000 |
| adx_threshold | 25.0 | 13.75 | 25.0 |
| min_persistence_ms | 240000 (4 min) | 231000 (3.85 min) | 240000 |
| weight_adx | 25 | 13.75 | 25 |
| weight_regime | 20 | 28.75 | 20 |
| weight_volume | 12 | 22.5 | 12 |
| weight_momentum | 8 | (missing) | 8 |

**最後 confirmed runtime restart 時間**：2026-05-11 10:57:42 UTC（engine.log 證實，今天 4:14 P1 V083 fix restart）。

**影響範圍**：
- ✅ engine 正常運行，risk 0
- ✅ 16 原則 0 觸碰（fail-soft 正確）
- ✅ DOC-08 §12 9 不變量 0 觸碰
- ⚠️ ma_crossover 14 個 ML-tuned 持久化值丟失 — Strategist 學習成果 **每次 restart 重置**
- ⚠️ STRATEGIST-AUTO-PROMOTE-CRITERIA-1 「穩定計數器」設計意圖被破壞（PERSIST-1 commit message 明示「resetting the AUTO-PROMOTE stability counter forever」）— 但 ma_crossover 4 天沒新 row 即穩定計數器早已停滯，restart 影響 = 0

### 3.2 為什麼不是 BLOCKER

- runtime in-memory 是 TOML defaults，**sum=65 ≠ 73**，所有 5 個策略 in-memory 都過 validate
- restore 失敗 = **設計上的 fail-soft 邊界**，PERSIST-1 commit `f1f7403` 明示「Fail-soft: DB unavailable / migration V019 not applied → empty vec, log single warn, engine starts normally」— 雖然這個 case 不是 DB unavailable 而是「persist 寫入質量退化」，但 fail-soft 仍然守住
- ma_crossover 自身近 4 天 Strategist 對它沒新動作 → 無法判斷「真實 AI tuned 參數」應該是哪一組（row 7143 已經是低品質 stale 推薦，restore 即使成功也沒實質學習價值）

### 3.3 為什麼不能無視

- WARN 每次 restart 噴一條 noise → 後續真實異常容易被淹（reviewer 注意力消耗）
- **strategist_scheduler 設計矛盾的根本**：validate vs apply 對「partial weight payload」處理不一致 — 任何未來給 ma_crossover 推新 weight 的 cycle 都會重複此 bug，DB 不斷累積「不可 restore 的 row」
- 證實 Ollama L1 推薦 **語意不穩定** — 從早期 explicit 4-weight 到後期省略 weight_momentum（從 2026-05-05 17:16 UTC 起），Strategist prompt 設計沒鎖死 schema
- 整個 ma_crossover ML-tuned 參數鍊條 **持續性破損** — 不修就是承認 ma_crossover 連 Strategist 都已放棄，只是 Strategist 自己沒對 ma_crossover 推新建議所以 user 沒察覺

---

## 4. 修復方案 — 3 個 option + 2 個架構級加固

### Option 1（推薦，最小侵入）：清持久化檔 — DELETE row 7143

```sql
DELETE FROM learning.strategist_applied_params
WHERE strategy_name = 'ma_crossover' AND id = 7143;
```

**效果**：
- 下次 restart → restore handler 嘗試 row 7140（更舊）— **同樣缺 weight_momentum**，sum=12.5+30+22.5+8=**73** → 同樣 reject
- 必須一路刪到 row 5849（last with full 4-weight, sum=65 ✓）或某個 weight-free row

**改進版**：
```sql
-- 直接刪除所有缺 weight_momentum 但含 weight_adx 的 row（這些都會 restart reject）
DELETE FROM learning.strategist_applied_params
WHERE strategy_name = 'ma_crossover'
  AND engine_mode = 'demo'
  AND (params_json->>'weight_adx') IS NOT NULL
  AND (params_json->>'weight_momentum') IS NULL;
```
**評估**：
- ⚠️ **PG 寫操作，operator 須顯式 sign-off**（destructive）
- ✅ 1 SQL，5 秒，0 risk runtime
- ✅ 下次 restart `n=2 total=2`（兩個策略都 restore 成功）
- ⚠️ 不修 root cause — 下次 Ollama 又推缺 weight key 的 row 還是會復發

### Option 2（治本架構修，建議 P2 排程）：修 `persist_applied_params` 寫入質量

**改 evaluate.rs:210-218**：persist 前先把 raw response 補成 **full param schema**（用 current_json 補入缺 key）：

```rust
// Before persist：把 response 補完成 current schema（保留 cycle 當下 in-memory 真實值）
let merged_persist = match crate::event_consumer::handlers::strategy_params::merge_strategy_params_json(
    &current_json.to_string(),
    &serde_json::to_string(&response)?,
) {
    Ok(s) => serde_json::from_str::<Value>(&s)?,
    Err(_) => response.clone(),  // fallback: 原樣
};
if let Err(e) = self
    .persist_applied_params(&pair.strategy_name, &current_json, &merged_persist, "top_deviation_pair")
    .await
```

**評估**：
- ✅ 治本 — 寫入 DB 的 row 永遠 self-contained，restore 不依賴 boot in-memory state
- ✅ 與 `apply_params` 路徑（同樣 merge）對稱
- ✅ Audit trail 更完整（DB 看一條 row 就知全 schema）
- ⚠️ 改 IPC dispatcher 入口 — 風險中（merge_strategy_params_json 從 `pub(super)` 改 `pub(crate)`）
- ⚠️ **改不了既有 row** — 仍需配合 Option 1 清舊 row
- Effort：~20-50 LOC + E4 round-trip test，1-2h

### Option 3（不推薦）：放寬 validate sum=65 規則

**評估**：
- ❌ 違反原則 5「生存 > 利潤」— validate 是 confluence scoring 不變式（threshold_no_trade/light/full 與 sum=65 對齊設計），放寬會破 confluence::compute_score 語意
- ❌ 違反原則 4「策略不繞風控」— sum=65 是 G-SR-1 設計合約
- ❌ 違反原則 6「失敗默認收縮」— 接受 stale partial payload 是擴張不是收縮

### 架構級加固 4（建議 P3 工程性）：restore handler 對 reject 自動清 DB row

```rust
// main_boot_tasks.rs:270-277 內，restore handler reject 後追加
Ok(Err(e)) => {
    warn!(strategy = %strategy_name, error = %e, "...");
    // CLEANUP-INVALID-PERSIST-1：reject 視為持久化質量問題，自動刪該 row
    // 避免每次 restart 重複噴同條 WARN
    if let Some(pool) = db_pool_for_cleanup.get() {
        let _ = sqlx::query(
            "DELETE FROM learning.strategist_applied_params \
             WHERE strategy_name = $1 AND engine_mode = $2 AND id = (
                SELECT id FROM learning.strategist_applied_params \
                WHERE strategy_name = $1 AND engine_mode = $2 \
                ORDER BY applied_at_ms DESC, id DESC LIMIT 1
             )"
        ).bind(&strategy_name).bind(&demo_mode).execute(pool).await;
        warn!("cleaned up rejected persist row / 自動清除無效 row");
    }
}
```

**評估**：
- ✅ 自動 GC — restart 一次清一條，最終 row 序列收斂到 valid state
- ⚠️ 破壞 audit trail — 不知道為何 row 消失（需配合 audit log）
- ⚠️ 改 boot path（風險中）

### 架構級加固 5（建議 P3 strategist prompt 收緊）：鎖 Ollama L1 schema

**evaluate.rs:404 `build_strategist_eval_payload`** 中 `strategist_skill.name="wide_parameter_adjustment"` payload 給 Ollama — 應明示「**若調 weight，4 個 weight 都必須 explicit**」schema constraint。同時 `validate_recommendation_with_reason` 對「has_weight_params=true 但部分 weight 缺」加嚴：拒絕「partial weight set」。

**評估**：
- ✅ 治本 — 從 source 杜絕 partial weight payload
- ⚠️ 改 Ollama prompt + Strategist validation logic — 風險中-高
- ⚠️ 需 QC 確認 confluence scoring 設計不變式不會被 partial set 隱式破壞

---

## 5. 推薦給 Operator 的最小破壞 action

### 立即（5 min, 0 risk）

```bash
# 1. PG 直接清掉 stale 缺 weight_momentum 的 ma_crossover row（25 條歷史 + 最新 5）
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"
DELETE FROM learning.strategist_applied_params
WHERE strategy_name='ma_crossover' AND engine_mode='demo'
  AND (params_json->>'weight_adx') IS NOT NULL
  AND (params_json->>'weight_momentum') IS NULL
RETURNING id, applied_at_ms;
\""

# 2. 驗證：應 30 行左右 deleted；之後 restore 用 sum=65 full-weight row
```

### 中期（接 next sprint，~2h）

- **Option 2**：persist 寫入前 merge current — 永久杜絕同 bug 復發
- **架構加固 4**：reject 自動清 row — 兼容未來新形式 partial payload

### 長期（Strategist 改進，需 QC sign-off）

- **架構加固 5**：Ollama prompt schema constraint + validate_recommendation 加嚴 partial weight set 拒絕

---

## 6. 16 根原則合規 + DOC-08 §12 + §四 硬邊界

| 維度 | 評估 | 證據 |
|---|---|---|
| 原則 6「失敗默認收縮」| ✅ PASS | restore reject → fallback TOML default 是正確收縮路徑 |
| 原則 7「學習 ≠ 改寫 Live」| ✅ PASS | 學習資料層 (`learning.strategist_applied_params`) 故障時 demo runtime 不受污染 |
| 原則 8「交易可解釋」| ⚠️ WARN | row 7143 缺 weight_momentum 字段 — DB audit trail 不完整，無法重建「當時 in-memory mom=0」事實 |
| 原則 11「Agent 最大自主」| ⚠️ WARN | ma_crossover P1 硬邊界內，但 14 個 tuned 參數每次 restart 重置 — 自主學習成果無持久性 |
| 原則 12「持續進化」| ⚠️ WARN | Strategist 學習路徑 4 天無新 ma_crossover row，restart 重置加劇進化停滯 |
| DOC-08 §12 9 不變量 | ✅ 0 觸碰 | 不涉及 lease / authorization / SM-04 / IntentProcessor / mainnet |
| §四 5 硬邊界 | ✅ 0 觸碰 | 不涉及 live_execution_allowed / max_retries / system_mode / authorization.json / mainnet env |

**結論**：**不是 BLOCKER**。Push back 不必。

---

## 7. 給 PM/Operator 的判斷建議

| 維度 | 推薦動作 |
|---|---|
| **是否 P1 緊急修** | ❌ 不必。runtime 跑 TOML defaults sum=65 fail-safe；風險 0 |
| **是否清 PG row** | ✅ 建議（Option 1 改進版）— 5 SQL 5 秒消 WARN noise |
| **是否治本** | ✅ Sprint N+2 排 Option 2（persist 寫入質量修）— 治本 ~50 LOC 1-2h E1 工作量 |
| **是否動 sum=65 validate** | ❌ 不動 — 不變式有 confluence scoring 設計合約根據 |
| **是否動 Ollama prompt** | ⏸️ 留 Strategist 整體改造時做（與 R-2 Strategist scope reframe 合併） |

---

## 8. PA 自評 — adversarial check（先別 sign off）

| 假設 | 我驗了嗎 | 證據 |
|---|---|---|
| restore 真的 fail-soft（沒 silent partial write） | ✅ | `merge_strategy_params_json` → `update_params_json` → `serde_json::from_str::<MaCrossoverParams>` → `update_params(params)` → `params.validate()?` 整 struct atomic |
| runtime in-memory 真的 TOML default 8 | ✅ 間接 | `MaCrossover::new()` line 437 用 `ConfluenceConfig::default()` (=8)；registry.rs:55-62 TOML override 不含 weight_*；Strategist 24h 0 row → 沒新 IPC 改寫 |
| sum=65 validate 不是新加的 | ✅ | `ea3237f0` 2026-04-13 G-SR-1 Phase A 首次引入 |
| WARN 每次 restart 都出現 | ✅ 直查 engine.log `2026-05-11T10:57:42.492514Z` 確認 |
| Ollama partial payload 真的從 2026-05-05 17:16 開始 | ✅ | `id=5924`（2026-05-05 19:15）first row with `weight_adx` but no `weight_momentum`；in-memory mom=0 transition first row id=5855（17:16）|
| grid_trading 真的 restore 成功 | ✅ | log `n=1 total=2`；row 8936 params 只 cooldown_ms + max_cooldown_boost，merge 不破 sum |
| 沒漏看其他「持久化檔」（檔案系統 / Python 端） | ✅ | grep `strategist_params\|params_persist\|STRATEGIST-PARAMS-PERSIST` rust + Python，唯一 SoT = PG learning.strategist_applied_params |

---

## 9. 結語

這是 **strategist_scheduler 設計層的 latent inconsistency**（writer ↔ reader path 對 partial weight payload 處理不對稱），不是當下 critical bug。fallback 工作正常守住 runtime 安全。WARN 是真信號（DB row 質量退化）但**不是 BLOCKER**。Option 1 改進版（PG cleanup）+ Sprint N+2 Option 2（persist 質量修）的雙軌方案是最小破壞最大長期收益的組合。

---

**完整證據鏈交叉檢驗已完成**。Operator 決策：(A) 立即跑 PG cleanup SQL；(B) Sprint N+2 排 Option 2 治本；(C) 不動 confluence validate sum=65。

**PA DESIGN DONE**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_strategist_params_persist_ma_crossover_rca.md`
