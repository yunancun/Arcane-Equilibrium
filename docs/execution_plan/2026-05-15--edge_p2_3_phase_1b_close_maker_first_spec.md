# EDGE-P2-3 Phase 1b — Close-Maker-First Refactor Spec

**Date**: 2026-05-15
**Author**: PM + PA + FA convergent audit chain (main session)；2026-05-15 PA round-2 patch v1.1（4-agent QC+FA+BB+MIT consolidated）；2026-05-15 PA Wave 1.5 patch v1.2（A3 portfolio_var verify + E3 maker fill empirical baseline + A4 W-C Caveat 2 V094 schema 兩段式 + writer gap）；2026-05-15 PA Wave 1.5b patch v1.3（Wave 3a 4-agent re-review consolidation — QC-MF-3 AC-5/AC-11 vs §1.2 fee saving 數學矛盾 + QC-SF-6 AC-18 Wilson-CI + MIT P3 stratification note + A3 §12.2 framing 微調）
**Status**: SPEC v1.3 — Wave 1.5b consolidated patch（AC-5/AC-11 +1.5 → +0.5 bps for n≥50 / directional only for n<30 + AC-18 Wilson-CI sub-clause + §12.2 line 758 entry-side framing 修正）；pending IMPL prereq 條件 2 (Wave 3a 4-agent re-review) + 3-gate
**Phase**: EDGE-P2-3 Phase 1b（entry-only Phase 1a 自然延伸到 close path execution-quality 軸；1c 留 microstructure；P2-4 留 alpha source promotion gate）
**Supersedes**: 無；補完 EDGE-P2-3 Phase 1a entry-only scope-limiting 設計決策
**對應 spec / TODO**: P0-EDGE-1 / EDGE-P2-3 / W-AUDIT-8b (alpha-source 後續) / DOC-01 §5.6 § §5.9 / DOC-08 §12

**Source verdicts**:
- PM: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--close_maker_first_pm_verdict.md` — APPROVED-CONDITIONAL
- PA: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md` — READY-FOR-SPEC
- FA round-1: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md` — APPROVED-CONDITIONAL
- 4-agent round-2 consolidated: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md` — 4/4 APPROVED-CONDITIONAL
- AMD v0.2: `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` — 17 must-fix + 14 should-fix integrated

---

## §1 背景與動機

### 1.1 經 3 輪對抗審核收斂的事實

| 事實 | 數據 / 來源 |
|---|---|
| 5 textbook 策略 30d net 虧損 | demo `-110.43` USDT / live_demo `-27.31` USDT |
| demo grid 7d active taker close | 203 筆，全 taker；分布 grid_close_short 97 / phys_lock_gate4_giveback 49 / bb_mean_revert 21 / grid_close_long 17 / phys_lock_gate4_giveback Sell 12 / bb_mean_revert Sell 4 / 其他 3 |
| live_demo grid 7d active taker close | 155 筆 **100% 策略級**（grid_close_short 115 / bb_mean_revert 28 / grid_close_long 11 / ma_reverse_cross 1），**0 真風控** |
| entry maker | 已實裝 + 100% maker fills (avg latency 5-14s, max ~50s) |
| close 路徑 | `srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:792-797` hard-coded `order_type:"market"` with comment「Close path stays Market (EDGE-P2-3 Phase 1a entry-only scope)」 |
| phys_lock_gate4 | profit-protection 4-gate 鏈（edge floor → hold age → peak ATR → giveback / stale ROC），非 §5.9 hard-stop |
| phys_lock live 7d 0 fires | by design：`risk_config_live.toml` 無 `missing_edge_fallback_bps` override → Rust default `-10.0` < floor `5.0` → Gate 1 永遠 Hold |
| Phase 1B-4.2 resting_orders.rs | paper-only，與 exchange close path 正交（PA 確認，**0 依賴**） |

### 1.2 預期經濟影響

**保守估算（v1.2 修正，per Wave 1 Track E3 empirical baseline）**：每筆 close attempt **`~0.5-2.0 bps net per close attempt`**（而非 v1.1 的 4.5 bps assumption / +0.65 bps net 推導）。
- **修正理由（E3 empirical 7d demo + live_demo entry maker baseline，per `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md`）**：
  - Best case (fill-conditional, Bybit fee saving): **~3.31 bps**（94% of fills are maker × 3.5 bps fee saving cap）
  - 中性 (per submitted with assumed fallback): **~0.95 bps**（27% PostOnly fill rate × 3.5 bps）
  - 悲觀 (close-path conservative discount 25-40%): **~0.66 bps per close attempt**（assumes close fill rate ≈ 20%，15-25% range）
  - **採用 0.5-2.0 bps net 保守 range**（而非單一 +0.65 bps 點估），cover empirical 不確定性 + close vs entry behavior 結構性差異
- **Bybit fee tier 0 baseline（per BB-SF-2 + E3 §6 confirmed）**：maker = 2.0 bps / taker = 5.5 bps；fee saving cap = 3.5 bps per side
- **live_demo grid 7d 155 active closes**（per §1.1）× $300 avg position × 0.5-2.0 bps × 1.2/h system rate ≈ **$50-$200 全年保守估**
- 跨 5 策略 + 25 symbols 全年估 **`~$50-$200 fee saving`**（v1.1 寫 $160-$400 太樂觀）
- **不能救 -110 USDT structural alpha deficit**（PM 判 P1，非 P0）
- 真正價值：消除執行成本掩蓋 alpha 信號，讓 P0-EDGE-1 edge measurement 更乾淨

**E3 empirical 三個意外發現（影響 spec 設計）**：
1. **`orders.intent_id` 100% NULL in 7d window**（writer 漏接 intent → order link）— 開新 P2 ticket `P2-ORDERS-INTENT-ID-WRITER-GAP-1` 修（不阻 Phase 1b IMPL，但影響 Guardian-pass-rate 計算）
2. **`orders.status` 100% Working**（fire-and-forget 初始狀態）— 終態 SOT 是 `order_state_changes.to_status`；healthcheck 必查 state_changes 不查 orders.status
3. **無 fallback to taker 機制**（70% PostOnly timeout 後 entry 直接放棄）— **此行為對 close path 不可繼承**（持倉繼續暴露 = 違 §二 #5 生存 > 利潤）；close 必加 mandatory fallback to taker（詳 §5.5）

**Net fee saving 推導（QC-SF-1，v1.1 推導保留作參考但 v1.2 採 E3 empirical range）**：
- 單筆 close fee delta = 5.5 - 2.0 = **3.5 bps**
- 假設 maker fill rate 70%（mirror entry side production-tested）→ avg fee saving per close = 3.5 × 0.70 = **2.45 bps**
- 扣 30% fallback overhead（timeout 期 adverse drift 估 ~6 bps）= 0.30 × 6 = -1.8 bps
- **保守淨估 = 2.45 - 1.8 ≈ +0.65 bps net per close**（v1.1 推導，**per E3 修正應視為「fill-conditional best case」非「per attempt」**）
- **E3 empirical per attempt 中性 = 0.95 bps，悲觀 = 0.66 bps**
- 對應 §11 AC-5 改 «改善 ≥ taker baseline 的 +1.5 bps» 保守 gate（不再是 +3 bps）

**Counterfactual cost simulation pre-IMPL evidence packet（QC-SF-2）**：IMPL 期間派 PA / E1 跑 historical 7d demo grid_close_short 數據 × estimated maker fill prob × bootstrap CI，產出 «预计 fee saving range + 95% CI» 報告（per AMD v0.3 §5.1 對應條目）。

### 1.3 不在本 spec 範圍

- ❌ 新 alpha 來源（funding / OI / OFI）→ W-AUDIT-8b/8a/8c
- ❌ Grid step 重算 → 待 close fee 改完再評估
- ❌ phys_lock live 啟用（`missing_edge_fallback_bps=10.0` override）→ DEFER 至 Phase 2b 後另開 PR
- ❌ Edge estimator pipeline 修復 → 獨立 P1
- ❌ MA KAMA fallback gate → scope-in W3-6 by-the-way（30 分鐘獨立修復，不依賴此 spec）

---

## §2 範圍與不變式

### 2.1 In-Scope

修改 `commands.rs:778-816` 中 close path 的 `OrderDispatchRequest` 構造，按 `trigger_tag` / `exit_reason` 白名單分流：
- 策略級 close：PostOnly Limit + maker_timeout_ms（fallback to market）
- 真風控 close：保持 hard-coded market（fail-safe 不變）
- 對 `ipc_close_all` (commands.rs:940) / `ipc_close_symbol` (commands.rs:1123) 兩個 dispatcher 同步應用相同規則

### 2.2 Out-of-Scope（顯式邊界）

- 不動 entry maker 邏輯（已驗證 100% maker fills）
- 不動 paper_state/resting_orders.rs（paper-only path 正交）
- 不動 stop_manager 風控邏輯（DYNAMIC/TRAILING STOP 仍 market）
- 不動 reconciliation engine close path（bybit_sync / orphan_adopted forced close 仍 market）

### 2.3 不變式（必須保持）

| 不變式 | 來源 | 保證機制 |
|---|---|---|
| 單一寫入口 | §二 #1 | close path 仍走 `execute_position_close → OrderDispatchRequest → order_dispatch_tx` 單通道 |
| 策略不繞風控 | §二 #4 | DYNAMIC/TRAILING STOP/HARD STOP/TAKE PROFIT/COST_EDGE 強制 market 不改 |
| 失敗默認收縮 | §二 #6 | Rust struct cold-boot `use_maker_close = false`；TOML 預設 demo=true / live=false（mirror Phase 1a） |
| 交易可解釋 | §二 #8 | 新欄位 `close_maker_attempt` / `close_maker_fallback_reason` 100% non-null（V### migration 配套） |
| 災難保護 | §二 #9 | engine shutdown / authorization 失效 → cancel_token 觸發 best-effort cancel pending maker close orders |
| W-C Caveat 2 不變式 | commands.rs:809-815 | close path 不寫 spine lineage；新欄位 audit 走 fills.details 不走 spine |
| 9 條安全不變量 | §四 | 9/9 PASS or PASS-with-stated-mitigation（FA verified） |

---

## §3 配置層設計

### 3.1 新增 strategy_params 欄位

每個策略 `[<strategy>]` section 新增：
```toml
use_maker_close = true               # demo/paper；live 預設 false
maker_close_price_offset_bps = 0.5   # 限價偏好我方多少 bps（過大易 reject，過小易 timeout）
maker_close_timeout_ms = 30000       # demo 30s；live 預設更短或保 market
# 可選 per-exit_reason override（透過後續 IPC patch 或 TOML 段落）
```

**Rust struct cold-boot default**: `use_maker_close = false`（§二 #6 fail-safe）。

### 3.2 新增 risk_config 欄位（可選）

`[exit]` section（與 phys_lock 配置同段）可加：
```toml
# Per-exit_reason close fallback policy (optional override)
close_maker_whitelist = [
  "grid_close_short", "grid_close_long",
  "bb_mean_revert",
  "phys_lock_gate4_giveback", "phys_lock_gate4_stale_roc_neg",
  "ma_reverse_cross", "bw_squeeze", "pctb_revert",
]
```

### 3.3 環境差異化

| 環境 | use_maker_close | 理由 |
|---|---|---|
| paper | true | 與 demo 對齊（per memory `feedback_demo_loose_live_strict_policy`） |
| demo | true | Phase 1b 預設啟用，驗收期 |
| live_demo | true（Phase 2b PASS 後）| 中段驗收，mirror entry Phase 1a 模式 |
| live (Mainnet) | **false 直到 operator 顯式 sign-off** | §二 #6 fail-safe + AMD requirement |

---

## §4 代碼層設計

### 4.1 commands.rs 三個 close dispatcher

| Dispatcher | 行號 | 改造 |
|---|---|---|
| `execute_position_close` | 778-816 | 加 maker 白名單分類器 + reuse compute_close_limit_price |
| `ipc_close_all` | 940（PA 確認） | 同上，按 trigger_tag 分流 |
| `ipc_close_symbol` | 1123（PA 確認） | 同上 |

**Reference 改造前後**：

改造前（commands.rs:792-797）：
```rust
order_type: "market".to_string(),
limit_price: None,
time_in_force: None,
// Close path stays Market (EDGE-P2-3 Phase 1a entry-only scope).
maker_timeout_ms: None,
```

改造後：
```rust
let (order_type, limit_price, time_in_force, maker_timeout_ms) =
    if self.is_close_maker_eligible(trigger_tag, &self.use_maker_close_cfg) {
        let limit = compute_close_limit_price(
            !is_long,                     // 平倉方向反向
            &maker_price_inputs,
            offset_bps,
            buffer_ticks,
            tick_size,
        );
        match limit {
            Some(price) => (
                "limit".to_string(),
                Some(price),
                Some("PostOnly".to_string()),
                Some(self.maker_close_timeout_ms_for(trigger_tag)),
            ),
            None => ("market".to_string(), None, None, None),  // strict-skip fallback
        }
    } else {
        ("market".to_string(), None, None, None)               // 保 market 真風控
    };
```

### 4.2 新增 `compute_close_limit_price()` helper

**推薦設計（PA Option C）**：
- 位置：`srv/rust/openclaw_engine/src/strategies/common/maker_price.rs`（與 entry side 同檔）
- 內部複用 `compute_post_only_price(is_long=反向, MakerPriceInputs, offset, buffer_ticks, ...)` strict-skip 模式
- 不同 per-exit_reason 行為通過 `buffer_ticks` + `offset_bps` 微調（不寫死多套 algorithm）

| exit_reason | buffer_ticks | offset_bps | timeout_ms | 理由 |
|---|---|---|---|---|
| grid_close_short / grid_close_long | 1 | 0.5 | 30000 | 翻轉信號，不急 |
| bb_mean_revert | 1 | 0.5 | 30000 | mean revert exit |
| ma_reverse_cross | 1 | 0.5 | 30000 | trend reverse |
| **phys_lock_gate4_giveback** | **1** | **0.5** | **15000** | **v1.1 QC-MF-2 修正**：原 v1.0 給 `buffer=2 / offset=1.0 / timeout=30000` 反向擴大 slippage（gate4 fire 時已是 peak ATR giveback，價繼續逆的條件期望 `E[Y\|maker_pending] < X` 嚴格小於 market 立即鎖）。修為 `buffer=1 / offset=0.5 / timeout=15000`，footnote ↓ |
| phys_lock_gate4_stale_roc_neg | 1 | 0.5 | 10000 | ROC<0 + stale 已偏弱，短 timeout |
| bw_squeeze / pctb_revert | 1 | 0.5 | 30000 | 樣本量低，conservative |

> **Footnote (QC-MF-2)**：phys_lock_gate4_giveback 的 timeout / buffer 參數選擇基於「gate4 fire condition 帶 unfavourable drift bias」— gate4 fire 時 peak ATR 已 surrender，下一秒價格繼續 unfavourable 的條件機率高於隨機 walk；故 maker pending 期 expected fill price 嚴格 worse than 立即 market；縮短 timeout + 收緊 buffer = 控制 unfavourable drift expose 視窗。

> **Footnote (BB-SF-3, small-tick alt symbol corner case)**：`compute_close_limit_price()` 必須 handle small-tick 1000-prefix 合約（1000PEPEUSDT / 1000BONKUSDT 等）— 這些 symbol tick_size = 0.000001，buffer_ticks=1 對應只 0.000001 USDT 偏移，可能小於 BBO spread 而被 PostOnly reject `EC_PostOnlyWillTakeLiquidity`。E1 IMPL 補：若 `tick_size * buffer_ticks < spread_bps / 2 * mid_price` → 自動 widen buffer 到滿足 strict-skip 邊界，否則 strict-skip 走 market。

> **Spread guard (QC-SF-4)**：`compute_close_limit_price()` 補 `spread_bps > 50 → strict-skip` 邏輯（與既有 PostOnly entry side `compute_post_only_price` 對齊）— 防 wide-spread book 下 maker 被吃成 worst-case slippage。

### 4.3 White / Black list 雙清單

**Positive whitelist (maker-first)** — 8 條：

| exit_reason | 來源 | FA 認可 |
|---|---|---|
| `grid_close_short` | grid_trading/signal.rs:316 | APPROVED |
| `grid_close_long` | grid_trading/signal.rs:348 | APPROVED |
| `bb_mean_revert` | bb_reversion/mod.rs:629（**FA correction：同策略 exit 非跨策略**） | APPROVED |
| `phys_lock_gate4_giveback` | exit_features/v2.rs Lock decision | APPROVED with named carve-out（§二 #4 PASS） |
| `phys_lock_gate4_stale_roc_neg` | exit_features/v2.rs Lock decision | APPROVED |
| `ma_reverse_cross` | ma_crossover/strategy_impl.rs | APPROVED |
| `bw_squeeze` | bb_breakout/mod.rs | CONDITIONAL（樣本量低，healthcheck `min_samples_gate=30`） |
| `pctb_revert` | bb_breakout/mod.rs:524-550 | CONDITIONAL（同上） |

**Negative whitelist (keep market)** — FA 識別的 5+ 條：

| exit_reason | 強制 market 理由 |
|---|---|
| `risk_close:HARD STOP: ...` | §5.9 P0/P1 硬止損 |
| `risk_close:TRAILING STOP: ...` | drawdown 真風控 |
| `risk_close:TIME STOP: ...` | 風控時間限制 |
| `risk_close:DYNAMIC STOP: ...` | 動態 ATR-based stop |
| `TAKE PROFIT: pnl X% >= Y%` | take profit 達標即收，maker 未成交違反設計 |
| `COST EDGE: ratio X >= 0.80` | §二 #13 cost_edge_ratio ≥ 0.8 = 建議關倉 |
| `DAILY LOSS / DRAWDOWN / CONSECUTIVE LOSS` | 帳戶級風控 |
| `bybit_sync` / `orphan_*` / `dust_frozen` | EX-04 reconciliation 觸發 |
| IPC `/operator/close_position` 強制平倉 | operator override 立即執行 |
| Engine shutdown / cancel_token / circuit breaker | §二 #9 災難保護 |
| **bb_breakout 內部 `trailing_stop`** | PA 識別 — 與 `risk_close:TRAILING STOP` 同 keyword 但屬策略決策；chandelier fire 時價已破線 maker 追不上 |

**分類器規則**：
- prefix-match `risk_close:` → 一律 market（顯式）
- bb_breakout 內部 `trailing_stop`：keep market（需 source 識別，非 prefix match）
- positive whitelist 全字符串 match → maker-first
- 未識別 reason → fail-closed 走 market（§二 #6）

### 4.4 Audit 欄位（V094 hybrid schema 強制決策，Consensus-MF-4）

**Migration slot**：**V094**（next-free，當前 max applied V093）。**File name**：`V094__fills_close_maker_audit.sql`（mirror V083 命名規範）。

**Hybrid schema design（明文，禁止 IMPL 階段分叉）**：

| 欄位 | 類型 | 載體 | 設計理由 |
|---|---|---|---|
| `close_maker_attempt` | `BOOLEAN NOT NULL DEFAULT FALSE` | **new column on `trading.fills`** | high-frequency group-by query（healthcheck [62] / [63] 都會 `GROUP BY close_maker_attempt`）；`partial index WHERE close_maker_attempt = true` 比 JSONB GIN 高效 100x |
| `close_maker_fallback_reason` | `TEXT NULL` (CHECK enum) | **new column on `trading.fills`** | enum allowlist 約束（CHECK constraint）+ healthcheck [63] NULL ladder 計算需獨立欄位；不適合 JSONB |
| `close_initial_limit_price` | `NUMERIC` | **`trading.fills.details` JSONB key** | 單筆 audit 讀取，無 group-by；JSON-column extension append-only（FA-MF-3 backward-compat） |
| `close_final_fill_price` | `NUMERIC` | **`trading.fills.details` JSONB key** | 同上 |
| `close_maker_eligible_reason` | `TEXT` | **`trading.fills.details` JSONB key** | 鏡像 trigger_tag，僅 audit 讀取 |

**enum allowlist（`close_maker_fallback_reason` CHECK constraint）**：
```sql
CHECK (close_maker_fallback_reason IS NULL OR close_maker_fallback_reason IN (
  'timeout_taker',                    -- maker timeout fallback to market
  'postonly_reject',                  -- EC_PostOnlyWillTakeLiquidity
  'cancel_grace_expired',             -- 2s cancel ack grace 過期
  'ack_lost',                         -- IPC ack 遺失，best-effort fallback
  'rate_limit_pause',                 -- TooManyPending 觸發
  'fast_escalate_safety_upgrade',     -- Race A：pending close + 新 risk trigger
  'not_attempted_safety_path',        -- 走 market 真風控（Negative whitelist）
  'engine_shutdown_safety'            -- cancel_token / authorization 失效
))
```

> **Safety path enum 重要**：`'not_attempted_safety_path'` + `'engine_shutdown_safety'` 是合法 close path，不是 audit 漏寫；healthcheck [63] NULL ladder 必須 **exclude 這兩個** 而非算進 NULL 比例（per Consensus-MF-3）。

**JSON 子欄位範例**（INSERT 寫入 `trading.fills.details` 對應 row）：
```json
{
  "close_initial_limit_price": 1234.56,
  "close_final_fill_price": 1234.50,
  "close_maker_eligible_reason": "grid_close_short"
}
```

**Linux PG dry-run mandatory**（per `feedback_v_migration_pg_dry_run.md` + V055/V083/V084 incident precedent）：
- E1 IMPL Mac 完成 → Linux PG **round 1**：`psql -f V094__fills_close_maker_audit.sql` + INSERT test data 驗 CHECK constraint reject 非 enum 值
- Linux PG **round 2**：再跑一次 V094，必須不 RAISE（idempotent verification）
- sqlx checksum verify：`bin/repair_migration_checksum` 處理 V094 file edit 後 DB checksum 同步
- E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID
- 禁 Mac mock pytest PASS = Linux PG runtime semantic PASS

**配套 healthcheck**：
- 新增 `[62] close_maker_fill_rate`（per Consensus-MF-2 Wilson-CI gate；§8.1）
- 新增 `[63] close_maker_fallback_audit`（per Consensus-MF-3 NULL ladder；§8.1）
- 新增 `[64] close_maker_rate_limit_pause_duration`（per BB-SF-1；§8.1）

**Backward-compat append-only（FA-MF-3）**：
- V094 純粹 ADD COLUMN + ADD CONSTRAINT，沒 ALTER existing column type / DROP column / RENAME column
- 既有 fills row 在 V094 apply 後：new column 取 default 值（`close_maker_attempt = FALSE`、`close_maker_fallback_reason = NULL`），既有 `details` JSONB 不被觸碰
- 既有 healthcheck 未引用新欄位 → 0 影響
- **如果 IMPL 階段 PA 改設計從 hybrid 變成 separate column → 必重評 backward-compat 影響 + 重派 4-agent review**

**Non-training surface invariant（MIT-MF-1，schema-level safety）**：

> 5 個 close_maker 欄位（new column 2 + JSONB key 3）是 **ops audit metadata**，禁餵任何 ML training pipeline（LinUCB / scorer / quantile / MLDE shadow / MLDE demo / DL3）。

E3 grep guard rule（永久）：
```bash
grep -nrE '(linucb|scorer|quantile|mlde|dl3).*close_maker_(attempt|fallback_reason|initial_limit|final_fill|eligible_reason)' program_code/
# 命中即 reject
```

**對齊 §五 SoT**：mirror `replay.simulated_fills 'synthetic_replay'` precedent — 建立 close_maker_* 為 exchange-side 真實 fill audit 專用 tier，禁 ML 端誤用。

### 4.5 修復現存 bug

**`reject_cooldown_until_ms` 不分 entry/close** — PA 識別：當前所有 maker rejection 共享一個 cooldown HashMap，entry reject 會凍住同 symbol 的 close path（反之亦然）。

**必拆**：`reject_cooldown_entry_until_ms` + `reject_cooldown_close_until_ms` 兩個獨立 map。順便修復不在本 spec scope 但無法繞過。

---

## §5 State Machine — 4 race scenarios

### 5.1 Race A：pending close + 新 risk trigger

**情境**：phys_lock_gate4_giveback maker pending 中（剩 20s timeout），TRAILING STOP fire。

**規則**：**fast-escalate**
1. Cancel pending maker close（best-effort，不等 ack）
2. 立即 market re-dispatch with 新 trigger_tag = TRAILING STOP
3. 寫 audit row：`close_maker_fallback_reason = "fast_escalate_safety_upgrade"`

### 5.2 Race B：maker timeout

**情境**：30s 到期未 fill。

**規則**：
1. Sweep 觸發 cancel
2. 等 cancel ack（或 grace period 2s）
3. Market re-dispatch with same trigger_tag
4. 寫 audit row：`close_maker_fallback_reason = "timeout_taker"`

### 5.3 Race C：reject `EC_PostOnlyWillTakeLiquidity` (PostOnlyCross)

**情境**：限價單已過市，PostOnly reject。

**規則**：**直接 market**（不重 quote — 價已過，重 quote 只會繼續 reject）
1. 寫 audit row：`close_maker_fallback_reason = "postonly_reject"`
2. **不**進 reject_cooldown（這是「價已過」而非「重複嘗試」）

### 5.4 Race D：reject `TooManyPending`（v1.1 BB-MF-2 dynamic backoff 取代 5min global pause）

**情境**：Bybit `EC_ReachMaxPendingOrders` (MakerRejectionCategory::TooManyPending) reject 觸發；當前 v1.0 設計「全域 5min pause」過度保守（Bybit V5 Order group 20 req/s per UID，rate-limit recovery 是 sub-second 級；5min 是 3000x overshoot，會 starve close path）。

**新規則（v1.1）**：

1. **Per-symbol dynamic backoff**：
   - 起始 backoff = **1s**
   - Binary exponential：每次同 symbol 連續 trigger TooManyPending → backoff `*= 2`
   - 上限 = **60s**
   - 重置條件：該 symbol 5min 內無 TooManyPending → backoff 重置 1s
   - 該 symbol close 路徑在 backoff 期間直接走 market；其他 symbol 不受影響

2. **Conditional global pause（防 cascade）**：
   - 若同一 1min window 內有 **≥ 10 個 distinct symbol 同時處於 backoff 狀態** → 升級全域 close maker pause 5min
   - 全域 pause 期間所有 symbol close 路徑走 market
   - 全域 pause 結束 → 所有 symbol backoff 重置 1s

3. **State 持久化**：
   - In-memory `HashMap<Symbol, BackoffState>`（per-symbol next_eligible_ms + consecutive_count）
   - 全域 `Option<u64>` global_pause_until_ms
   - engine restart 後重置（accepted trade-off：rate-limit state 不跨 process boundary）

4. **Audit row 標記**：
   - per-symbol backoff 觸發 → `close_maker_fallback_reason = "rate_limit_pause"`（既有 enum）
   - global pause 觸發 → `close_maker_fallback_reason = "rate_limit_pause"` + `details.rate_limit_scope = "global"` JSONB 子欄位

**Pre-IMPL prove**：dispatch dry-run test 驗 binary exp 邏輯 + 10-symbol cascade 觸 global pause 行為。

**估算 IMPL 工作量**：~50 LOC backoff state machine + ~80 LOC integration test。

### 5.5 Race E：Fallback to taker mandatory（v1.2 新增，per Wave 1 Track E3 finding）

**問題**：Track E3 7d empirical baseline（per `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md`）證實當前 entry-side 70% PostOnly timeout **直接放棄**（無「Limit cancelled → 同 intent 後續 Market re-dispatch」pattern；engine 當前無 fallback to taker 機制，只有 ipc_close_symbol risk-close 用 Market）。

**對 entry path 的影響可接受**（missed entry 只是錯過開倉機會，無持倉風險）；**對 close path 不可接受**（close = 必須減 exposure；放棄 = 持有不利倉位 = 違 §二 #5 生存 > 利潤）。

**規則（強制 invariant，IMPL 必加）**：

1. **任何 close maker fallback path 必 fallback to taker market**：
   - **Race B (maker timeout)**：cancel ack（或 grace 2s）後 market re-dispatch with same trigger_tag → 寫 `close_maker_fallback_reason = "timeout_taker"`
   - **Race C (PostOnly reject)**：直接 market（不重 quote）→ 寫 `close_maker_fallback_reason = "postonly_reject"`
   - **Race D (TooManyPending backoff)**：per-symbol backoff 期間直接 market → 寫 `close_maker_fallback_reason = "rate_limit_pause"`
   - **engine cancel_token / authorization 失效**：cancel pending + 後續 close 走 market → 寫 `close_maker_fallback_reason = "engine_shutdown_safety"`
   - **任何「unknown reject」**：fail-closed 走 market → 寫 `close_maker_fallback_reason = "ack_lost"`（既有 enum）

2. **禁止「放棄」（abandon）路徑** — 任何 close maker pending 結束（成功 / 超時 / reject / cancel ack）後若仍未平倉 → 必 dispatch market；engine 不應讓 close intent silent dropping。

3. **IMPL gate（E1 IMPL prereq）**：
   - 加 unit test `test_close_maker_timeout_must_fallback_to_market`：close maker pending 30s 未 fill → assert market re-dispatch within 1 tick after cancel ack（per `event_consumer/pending_sweep.rs`）
   - 加 unit test `test_close_maker_postonly_reject_must_fallback_to_market`：PostOnly reject → assert immediate market re-dispatch
   - 加 unit test `test_close_maker_engine_shutdown_must_fallback_to_market`：cancel_token fired 後 pending close → assert best-effort cancel + 後續 close intent 走 market（不丟）

4. **healthcheck `[62] close_maker_fill_rate` 補 sub-check（per Wave 1 Track E3 finding）**：
   - 新 sub-metric `close_maker_fallback_to_taker_rate ≥ 95%`：close maker attempt 中 fallback to taker（任何 reason）的比例 ≥ 95%
   - 5% race window allowance（real-fill / pending dispatcher 邊界 race / engine restart inflight）
   - 公式：`fallback_to_taker_rate = COUNT(close_maker_attempt AND close_maker_fallback_reason IN ('timeout_taker','postonly_reject','rate_limit_pause','engine_shutdown_safety','ack_lost','fast_escalate_safety_upgrade')) / COUNT(close_maker_attempt AND fill_status != 'maker_fill')`
   - PASS: ≥ 95%
   - WARN: 90-95%
   - FAIL: < 90%（possible silent abandonment regression）
   - **v1.3 footnote (per QC-SF-6)**：上述 PASS/WARN/FAIL 為 point estimate；Wilson-CI gating per QC-SF-6（IMPL phase healthcheck [62] sub-check SQL 補 Wilson 計算）— per env 7d Wilson 95% CI lower vs 95%；CI lower < 90% → WARN；CI lower < 85% → FAIL（mirror AC-14 mechanism）。對齊 §11.7 AC-18 sub-clause。

5. **Audit row enum invariant**：
   - 任何 close maker attempt 結束時 fill_status `≠ 'maker_fill'` → `close_maker_fallback_reason` 必 NOT NULL（不可 NULL，per §4.4 enum allowlist 已 cover）
   - 對應 §11 AC-18 補 `close_maker_fallback_to_taker_rate ≥ 95% over 7d`

**估算 IMPL 工作量**：~30 LOC fallback dispatch hook + ~120 LOC unit test（3 case × ~40 LOC）。

---

## §6 Reject + Cooldown 處理

### 6.1 cooldown 拆分（修現存 bug，BB-MF-3 升 P0 priority）

**問題嚴重度（v1.1 BB 提升）**：當前 `reject_cooldown_until_ms` 不分 entry/close（grid_trading/signal.rs:152-158 per-symbol cooldown），entry side 觸 rate-limit-adjacent 條件後 → close path silent degradation 永遠走 market（失去整個 maker 優化價值）。**這個 fix 是 prerequisite，不是 by-the-way scope** — AMD v0.2 §8 IMPL prereq 第 6 條明文要求 pre-Phase 2a Demo enable 必 land。

| 欄位 | 用途 | 值（v1.1 修正：dynamic backoff 取代固定 5min）|
|---|---|---|
| `reject_cooldown_entry_until_ms` | entry maker reject cooldown | 沿用既有邏輯 |
| `reject_cooldown_close_until_ms` | close maker reject cooldown | **per-symbol dynamic backoff（per §5.4）**：TooManyPending → 1s exp → 60s 上限；其他 reject → 1min |

**驗證**：`event_consumer/cooldown_isolation_tests.rs` 新增 entry reject 不影響 close path regression test。

### 6.2 maker_rejection.rs 擴展（BB-MF-4 enum reuse；不新建 CloseTooManyPending / ClosePostOnlyCross variant）

**v1.1 設計修正（BB-MF-4）**：原 v1.0 提議新建 `Self::CloseTooManyPending` / `Self::ClosePostOnlyCross` variant 是錯的；BB 立場：

> **Bybit reject reason 字典**（字典 §4.2.1）：`EC_PostOnlyWillTakeLiquidity` 的 mechanical condition 對 entry/close 是相同的，與訂單 side 無關。新建 close-side variant 等於把同一個 Bybit error code 拆成兩個 Rust enum case，破壞 enum 1:1 mapping invariant。

**正確設計（v1.1）**：**復用既有 entry side enum + side flag**

```rust
// MakerRejectionCategory 不變
pub enum MakerRejectionCategory {
    PostOnlyCross,      // EC_PostOnlyWillTakeLiquidity（entry + close 同 enum case）
    TooManyPending,     // EC_ReachMaxPendingOrders（同上）
    // 其他既有變體
}

// dispatch handler 加 side flag 判斷處理路徑
fn handle_maker_rejection(
    category: MakerRejectionCategory,
    side: OrderSide,        // Entry / CloseLong / CloseShort
    symbol: &str,
    /* ... */
) {
    match (category, side) {
        (PostOnlyCross, OrderSide::Entry) => { /* 既有 entry 處理：cooldown 1min */ }
        (PostOnlyCross, OrderSide::CloseLong | OrderSide::CloseShort) => {
            // §5.3 Race C：直接 market，不進 close cooldown
            write_audit("postonly_reject");
        }
        (TooManyPending, OrderSide::Entry) => { /* 既有 entry 處理 */ }
        (TooManyPending, OrderSide::CloseLong | OrderSide::CloseShort) => {
            // §5.4 Race D：per-symbol dynamic backoff
            apply_close_backoff_per_symbol(symbol);
            write_audit("rate_limit_pause");
        }
        _ => { /* 其他既有處理 */ }
    }
}
```

**字典手冊更新**（BB-MF-1，**P1 backlog Wave 3 BB1 處理，本 spec 不動字典手冊**）：
- 字典 §1.2 顯式記錄「PostOnly + reduceOnly 並用合法」+ reject 行為對 entry/close 無區別
- 字典 §4.3 加 demo endpoint PostOnly silent degradation 警告
- 本 spec 僅引用 / 標 TODO，留 Wave 3 BB1 實際更新

---

## §7 Timeout + Sweep

### 7.1 Timeout 設計

| 策略 / reason | timeout_ms | 理由 |
|---|---|---|
| 大部分策略級 | 30000 (30s) | entry maker avg 5-14s, max 50s；30s 涵蓋 p90 fill window |
| `phys_lock_gate4_stale_roc_neg` | 10000 (10s) | ROC<0 + stale 已偏弱，倉位 expose 久不利 |

**未來考量（Phase 1b+）**：ATR-aware timeout（vol 高短 timeout / vol 低長 timeout）— 不在 Phase 1b scope。

### 7.2 Sweep 複用

`event_consumer/pending_sweep.rs` 既有邏輯**不分 close/entry**，只看 `time_in_force == PostOnly` + `maker_timeout_ms`。**0 改動 sweep 邏輯**，close maker 自動受其管理。

---

## §8 Healthcheck + Observability

### 8.1 新增 passive_wait_healthcheck（v1.1：Wilson CI + sample-size + NULL ladder + reject sample）

```python
def check_close_maker_fill_rate():
    """
    [62] close_maker_fill_rate — Phase 1b 部署後 PASS gate
    （v1.1 Consensus-MF-2：sample-size + Wilson-CI gating，取代 v1.0 point estimate）

    Per-strategy / per-exit_reason 分層判斷：
    - n < 30 → NEUTRAL（不放入 PASS/FAIL 分母，per MIT-MF-2 + MIT-SF-3 normative AC）
    - 計算 Wilson 95% CI 取下界 (lower) + 上界 (upper)
    - PASS: Wilson CI lower ≥ 60%
    - WARN: Wilson CI lower ∈ [40%, 60%)
    - FAIL: Wilson CI upper < 40%

    bw_squeeze / pctb_revert min_samples_gate=30 升 normative AC
    （v1.0 carve-out 注釋 → v1.1 升正式 gate per MIT-SF-3 + MIT-MF-2）
    """

    # 範例 SQL（per-exit_reason 分層）
    """
    SELECT
        strategy_name,
        details->>'close_maker_eligible_reason' AS exit_reason,
        COUNT(*) FILTER (WHERE close_maker_attempt = TRUE) AS attempts,
        COUNT(*) FILTER (WHERE close_maker_attempt = TRUE
                         AND close_maker_fallback_reason IS NULL) AS fills,
        COUNT(*) FILTER (WHERE close_maker_attempt = TRUE
                         AND close_maker_fallback_reason IS NOT NULL) AS fallbacks
    FROM trading.fills
    WHERE created_at >= NOW() - INTERVAL '7 days'
      AND env IN ('demo', 'live_demo')
    GROUP BY 1, 2
    HAVING COUNT(*) FILTER (WHERE close_maker_attempt = TRUE) >= 30  -- min_samples_gate
    """
```

```python
def check_close_maker_fallback_audit():
    """
    [63] close_maker_fallback_audit — audit 完整性
    （v1.1 Consensus-MF-3：NULL rate 階梯 + safety path enum allowlist）

    NULL rate 階梯計算（exclude safety path enum allowlist）:
    null_rate = COUNT(close_maker_attempt = TRUE
                      AND close_maker_fallback_reason IS NULL
                      AND fill_status = 'closed_by_market'  -- 非 maker fill
                     ) / COUNT(close_maker_attempt = TRUE AND fill_status != 'open')

    Safety path（不算 NULL）:
    - 'not_attempted_safety_path'（走 market 真風控）
    - 'engine_shutdown_safety'（cancel_token / authorization 失效）

    PASS: null_rate ≤ 0.1%
    WARN: 0.1% < null_rate ≤ 1.0%
    FAIL: null_rate > 1.0%

    對齊 V083 base 7d 已知 close fill entry_context_id 2.8-3.4% NULL fail-soft tail。
    """
```

```python
def check_close_maker_rate_limit_pause_duration():
    """
    [64] close_maker_rate_limit_pause_duration — backoff 健康度（per BB-SF-1）

    per env 7d 累計 backoff time:
    - per_symbol_pause_sec = SUM(per-symbol backoff duration)
    - global_pause_sec = SUM(global pause duration when triggered)

    Per-symbol thresholds（per day average）:
    - PASS: ≤ 5 min/day per symbol
    - WARN: 5-30 min/day per symbol
    - FAIL: > 30 min/day per symbol

    Global pause thresholds:
    - PASS: ≤ 5 min/day
    - WARN: 5-30 min/day
    - FAIL: > 30 min/day
    """
```

### 8.2 metric 追加

| metric | 用途 |
|---|---|
| `close_maker_attempted_total` | 已嘗試 maker close |
| `close_maker_fill_total` | maker 成交 |
| `close_maker_timeout_to_taker_total` | timeout fallback |
| `close_maker_reject_postonly_total` | PostOnlyCross reject |
| `close_maker_rate_limit_pause_active` | gauge 0/1 |
| `close_maker_per_symbol_backoff_active` | gauge per-symbol（v1.1 BB-MF-2 dynamic backoff）|
| `close_maker_global_pause_total_seconds` | counter（v1.1 BB-SF-1 [64] 配套）|

### 8.3 Reject sample healthcheck（BB-MF-5，Phase 2a Demo silent degradation 防護）

```python
def check_close_maker_reject_samples():
    """
    [65] close_maker_reject_samples — Phase 2a Demo PASS criteria（per BB-MF-5）

    防 demo endpoint PostOnly + reduceOnly silent degradation：
    Bybit demo doc 不顯式聲明 demo endpoint 對 PostOnly close 的 reject 推送行為，
    7d 0 reject sample 可能是 demo silent degradation（不能 promote Phase 2b）。

    PASS criteria（per env 7d）:
    - EC_PostOnlyWillTakeLiquidity reject sample count ≥ 1
    - EC_ReachMaxPendingOrders reject sample count ≥ 1
    （per category，至少各 1 樣本確認 Bybit demo endpoint 真的會推送 reject）

    若 7d 0 樣本 → upgrade Phase 2b LiveDemo 前必跑 mainnet probe 驗 reject 推送
    """
```

---

## §9 Test 影響面

### 9.1 既有測試

PA grep 確認受影響 reason-string assert（**reason 字串不變不破**）：
- `grid_trading/tests.rs` 4 處
- `ma_crossover/tests.rs` 3 處
- `bb_reversion/tests.rs` 2 處
- `bb_breakout/tests.rs` 1 處

合計 10 處，reason 字串保留，**無 breakage 風險**。

### 9.2 新增測試（v1.1 增 dynamic backoff + spread guard + small-tick）

| 測試 | 文件 | 覆蓋 |
|---|---|---|
| Whitelist classifier unit | `commands_close_maker_tests.rs` | 8 maker + N market 全 case |
| compute_close_limit_price unit | `common/maker_price_close_tests.rs` | strict-skip / per-reason buffer / inverted is_long / **spread_bps > 50 strict-skip (QC-SF-4)** / **small-tick alt symbol (BB-SF-3)** |
| State machine 4 race integration | `tick_pipeline/close_maker_race_tests.rs` | A/B/C/D 各場景 |
| cooldown 拆分 regression | `event_consumer/cooldown_isolation_tests.rs` | entry reject 不影響 close path |
| Sweep close maker reuse | `event_consumer/pending_sweep_close_tests.rs` | timeout fallback to market |
| Rollback kill-switch | `commands_close_maker_rollback_tests.rs` | TOML flag flip → 1 tick 內 market |
| Audit field non-null | `database/fills_audit_close_maker_tests.rs` | NULL ladder 階梯 + safety path enum (v1.1 Consensus-MF-3) |
| **Dynamic backoff (v1.1 BB-MF-2)** | `event_consumer/close_maker_dynamic_backoff_tests.rs` | per-symbol 1s→60s exp + 10-symbol cascade → global pause 行為 |
| **Wilson CI per-strategy gate (v1.1 Consensus-MF-2)** | `helper_scripts/db/passive_wait_healthcheck_tests.py` | n<30 → NEUTRAL / CI lower vs 60% / CI upper < 40% FAIL |
| **Non-training surface invariant grep guard (v1.1 MIT-MF-1)** | `helper_scripts/audit/e3_grep_non_training_surface.sh` | `program_code/**/{ml,training,learning,scorer,linucb,mlde,dream,dl3}/` 不出現 close_maker_* |
| **W-C Caveat 2 spine lineage guard (v1.1 FA-MF-2/F-FA-3)** | `agent_spine/lineage_guard_tests.rs` | 任何 close_maker_* INSERT 路徑不寫到 `agent_spine.*` 任何 table |

E1 估計：~400 LOC tests + ~150 LOC v1.1 新增 = **~550 LOC tests**。

---

## §10 Rollout — demo → live_demo → live

### 10.1 三段灰度（mirror EDGE-P2-3 Phase 1a entry 模式；v1.2 加 14d pilot observation per Track E3 conservative discount）

| 階段 | 期間 | 環境 | 啟用方式 |
|---|---|---|---|
| Phase 2a Demo | **7d primary + 7d extended observation = 14d total** | demo | TOML `use_maker_close=true` / per-策略獨立 flag |
| Phase 2b LiveDemo | 7d (Phase 2a 14d PASS 後) | live_demo | TOML override per-策略 |
| Phase 3 Live | indefinite | live (Mainnet) | **operator 顯式 sign-off** + AMD 補件 |

**Phase 2a 14d 拉長理由（v1.2，per Track E3 §8 conservative discount）**：
- E3 預估 close maker fill rate **15-25%**（vs entry 27%），若 7d primary 樣本量不足判斷 close-maker fill rate 穩定性
- Phase 2b 不適用（real-fill behavior 較難進一步驗證），Phase 2a 必需 14d 確認 fill rate stability
- Phase 2a PASS gate **新加 AC-19**：14d extended observation `close_maker_fill_rate ≥ 30%`（per E3 推薦「conservative discount」）
- 7d primary 觀察期：跑 AC-1..AC-17 + AC-18（fallback to taker rate）+ AC-14/15/16 baseline
- 7d extended observation：純樣本累積 + close-maker fill rate stability check；若 14d total close-maker fill rate < 30% → Phase 2b BLOCKED + spec 修訂或 reject

### 10.2 Kill-switch

| 觸發 | 動作 |
|---|---|
| TOML hot-reload `use_maker_close=false` | ArcSwap 1 tick 內回 market |
| `close_maker_fail_rate > 50% over 5min` | IPC `/operator/risk/exit_patch` 自動 disable + alert |
| Engine shutdown / authorization 失效 | cancel_token 觸發 best-effort cancel pending |

---

## §11 Per-stage PASS Criteria（v1.1 — AC-1..AC-13 連續編號 + AC-14/15/16 新增 4-agent must-fix；v1.3 patch — AC-5 / AC-11 / AC-18 修正以對齊 §1.2 fee saving range）

> **Footnote v1.3 patch (per QC-MF-3 round 3 review)**：v1.1 留設的 AC-5 / AC-11 「+1.5 bps Δ vs taker baseline」與 v1.2 §1.2 fee saving revision 「0.5-2.0 bps net per close attempt（中性 0.95）」內部矛盾 — +1.5 bps gate > 0.95 bps 中性估計 → Phase 2a 14d empirical 跑出 close fill rate ~20-25% 後 AC-5 deterministically FAIL。v1.3 改 AC-5 「**+0.5 bps for n≥50 cells / directional improvement only (≥ 0) for n<30 cells**」+ AC-11 「**+0.5 bps**」對齊 §1.2 conservative range 下界。
>
> **Footnote v1.3 patch (per QC-SF-6 round 3 review)**：v1.1 §11.7 AC-18 + §5.5 line 410-411 是 point estimate「PASS ≥ 95% / WARN 90-95% / FAIL < 90%」，small-n window 容易誤判。v1.3 補 Wilson-CI sub-clause（mirror AC-14 mechanism；IMPL phase healthcheck [62] sub-check SQL 補 Wilson 計算）。

### 11.1 Phase 2a Demo PASS（最早 2026-05-29+ 7d 觀察）

| AC | 內容 |
|---|---|
| AC-1 | demo close maker 比例 ≥ 60%（**WARN @ 65% threshold**，per QC-SF-3 — breakeven 57% margin 太窄，65% 給安全邊際）|
| AC-2 | fallback (maker_timeout → taker market) 比例 ≤ 30% |
| AC-3 | `close_dispatch_failed` counter 不增 |
| AC-4 | per-strategy 5 close exit_reason 各自 close fill ≥ 10 條（bw_squeeze/pctb_revert 各 ≥ 1，套 §4.3 carve-out gate；min_samples_gate=30 升 normative AC per MIT-SF-3）|
| AC-5 | close 平均 net_bps 改善 **≥ taker baseline 的 +0.5 bps for n≥50 cells**；directional improvement only **(≥ 0) for n<30 cells**（v1.3 修正 per QC-MF-3 + Wilson-CI gating per Consensus-MF-2 mechanism；對齊 §1.2 conservative range 下界 0.5-2.0 bps net per close attempt 中性 0.95；原 v1.1 +1.5 bps gate 與 §1.2 fee saving revision 數學矛盾，n≥50 + n<30 階梯為 sample-size 配套保護）|
| AC-6 | `trading.fills` 中 `close_maker_attempt` + `close_maker_fallback_reason` non-null **NULL ladder 階梯（v1.1 Consensus-MF-3）**：PASS NULL rate ≤ 0.1% / WARN 0.1-1.0% / FAIL > 1.0%；`'not_attempted_safety_path' / 'engine_shutdown_safety'` 入 enum allowlist 不算 NULL |
| AC-7 | 健康檢查 `[62][63][64][65]` PASS 7d 持續 |

### 11.2 Phase 2b LiveDemo PASS（再 7d）

| AC | 內容 |
|---|---|
| AC-8 | LiveDemo Phase 2a 同等指標滿足（含 AC-14/15/16）|
| AC-9 | authorization.json HMAC re-verify 期間 0 stray pending maker close orders |
| AC-10 | MAG-082/083/084 全 ✅ 維持，無 regression（W-C lease lineage 寫入正常）|
| AC-10b | **Phase 2b 7d fresh holdout 評估（v1.1 QC-SF-5）**：Phase 2a → 2b 不能直接 cross-validate；Phase 2b 必獨立評估 in-sample overfit 防護 |

### 11.3 Phase 3 Live（Mainnet only）

| AC | 內容 |
|---|---|
| AC-11 | Phase 2b 14d 內 0 P0 regression + close net_bps Δ vs Phase 1a baseline **≥ +0.5 bps**（v1.3 修正 per QC-MF-3，對齊 §1.2 conservative range 下界 0.5-2.0 bps net per close attempt；原 v1.1 +1.5 bps 與 §1.2 fee saving revision 數學矛盾）|
| AC-12 | operator 顯式 sign-off |
| AC-13 | AMD 補件（live carve-out + 翻 flag posture） |

### 11.4 全階段共通 statistical AC（v1.1 4-agent consensus must-fix）

| AC | 內容 |
|---|---|
| **AC-14** | **Wilson CI gate（v1.1 Consensus-MF-2）**：per-strategy / per-exit_reason 統計判定須採 Wilson 95% CI 下界 vs 60% threshold 而非 point estimate；n<30 → NEUTRAL；CI upper < 40% → FAIL |
| **AC-15** | **Reject sample healthcheck（v1.1 BB-MF-5）**：每 env 7d 至少 ≥ 1 sample per `EC_PostOnlyWillTakeLiquidity` / `EC_ReachMaxPendingOrders` reject category；0 樣本 → upgrade Phase 2b 前必跑 mainnet probe 驗 demo endpoint silent degradation 不存在 |
| **AC-16** | **NULL ladder（v1.1 Consensus-MF-3）**：`close_maker_attempt = TRUE AND close_maker_fallback_reason IS NULL AND fill_status = 'closed_by_market'` ratio NULL rate 階梯 PASS ≤ 0.1% / WARN 0.1-1.0% / FAIL > 1.0%；safety path enum (`'not_attempted_safety_path'` / `'engine_shutdown_safety'`) 不算 NULL |

### 11.5 Multiple testing 修正（v1.1 QC-MF-1）

Phase 2a → 2b → 3 共 3 phase × 8 exit_reason × 2 env = **48 test points** 累積測試，每 cell 跑 AC-1..AC-16 評估 → 必採 **FDR 0.10 with Benjamini-Hochberg procedure**（不採 Bonferroni 太嚴）。

詳：AMD v0.2 §5.1 multiple testing protocol。

### 11.6 Phase 2a Demo close_timeout_pre_stopout_rate AC（v1.1 FA round-1 #5）

| AC | 內容 |
|---|---|
| AC-17 | `close_timeout_pre_stopout_rate ≤ 5%` per env 7d — maker timeout 期間真風控 fire 比例必 ≤ 5%（防 #5 生存 > 利潤 expose 風險）|

### 11.7 Wave 1.5 v1.2 新增 AC（per A3 + E3 finding）

| AC | 內容 |
|---|---|
| **AC-18** | **`close_maker_fallback_to_taker_rate ≥ 95% over 7d`** per env（v1.2 §5.5 race fallback gap 新增，per Wave 1 Track E3 finding：當前 entry path 70% PostOnly timeout 直接放棄，close path 不可繼承此行為；fallback to taker rate < 95% = 可能 silent abandonment regression，違 §二 #5 生存 > 利潤）。**v1.3 sub-clause (per QC-SF-6)**：per env 7d 樣本算 Wilson 95% CI lower vs 95%；CI lower < 90% → WARN；CI lower < 85% → FAIL（mirror AC-14 mechanism；point estimate gating 在 small-n 容易誤判，IMPL phase healthcheck [62] sub-check SQL 補 Wilson 計算 per QC-SF-6） |
| **AC-19** | **14d extended observation `close_maker_fill_rate ≥ 30%`**（v1.2 §10.1 14d pilot 新增，per Wave 1 Track E3 conservative discount：close fill rate 預估 15-25% vs entry 27%，14d 確認 fill rate stability；< 30% → Phase 2b BLOCKED + spec 修訂或 reject）|

---

## §12 Risk + Mitigation

### 12.1 PA 識別的技術 risk

| Risk | 等級 | Mitigation |
|---|---|---|
| Dispatch 點白名單分類器（3 處 + free-text trigger_tag） | HIGH | E2 + A3 + E4 必審 + grep guard test |
| bb_breakout `trailing_stop` 歧義（vs `risk_close:TRAILING STOP`） | HIGH | 必 prefix-match `risk_close:` 區分；E2 必加 grep guard |
| reject_cooldown cross-side 污染 | MEDIUM | 拆分 entry/close cooldown（順手修現存 bug） |
| Rate-limit 競爭 | MEDIUM (NEEDS-PROBE) | 25 symbol grid 7d close 203 筆 ≈ 1.2/h，sweep cycle 突發風險低；TooManyPending 全域 5min pause mitigation |
| State machine fast-escalate IPC | MEDIUM | +2 `PendingOrderEvent` variant + dispatch handler integration test |
| Tests 影響面 | LOW | 10 reason-string assert 不破 |
| Phase 1B-4.2 依賴 | LOW | 0 依賴（PA 確認 paper-only orthogonal） |
| **Close maker fallback「直接放棄」可能 inherit entry-side gap（v1.2 新增，per Track E3 finding）** | **HIGH** | §5.5 mandatory fallback to taker invariant + AC-18 95% rate gate + 3 unit test（timeout/postonly_reject/engine_shutdown） + healthcheck [62] sub-check |

### 12.2 FA 識別的功能 / 合規 risk

| Risk | 等級 | Mitigation |
|---|---|---|
| §二 #5 生存 > 利潤 maker timeout 期 expose 風險 | CONDITIONAL | `phys_lock_gate4_stale_roc_neg` timeout 降到 10s；AC-2 fallback ≤30%；AC 必含 close_timeout_pre_stopout_rate ≤ 5% |
| §二 #6 失敗默認收縮 | CONDITIONAL | cold-boot=false / live 預設不啟用 / 三段灰度 |
| §二 #8 交易可解釋 | CONDITIONAL | 新欄位 V### migration（F-FA-1 P1） |
| §二 #9 災難保護 pending maker on shutdown | CONDITIONAL | cancel_token 路徑 cancel_resting_maker_order best-effort；authorization 失效 → 清 pending |
| §二 #16 entry-side resting maker pending 期 portfolio under-estimate（既有 systemic gap，新 P1 ticket option A 平行解；per Wave 1 Track A3 verify finding，close path is_reducing→allow() 不觸 portfolio gate 不引入新 risk vector；v1.3 framing 對齊 QC §7 反問 5）| CONDITIONAL | `P1-PORTFOLIO-RESTING-EXPOSURE-1` 平行 IMPL（A3 verify report §8 + §15 ticket scope）|

### 12.3 量化 risk - 9 條安全不變量

FA 評估：9/9 PASS or PASS-with-stated-mitigation；**無 BLOCKER**。

---

## §13 合規對照

### 13.1 §二 16 條根原則（PASS / CONDITIONAL）

| 原則 | 判定 |
|---|---|
| #1 單一寫入口 | PASS |
| #3 AI→Lease→複核→執行 | PASS |
| #4 策略不繞風控 | PASS（phys_lock_gate4 是 profit-protection 非 hard-stop，FA 確認） |
| #5 生存 > 利潤 | CONDITIONAL（§12.2 mitigation） |
| #6 失敗默認收縮 | CONDITIONAL（cold-boot=false / 三段灰度） |
| #7 學習 ≠ 改寫 Live | PASS |
| #8 交易可解釋 | CONDITIONAL（新欄位 mandatory） |
| #9 災難保護 | CONDITIONAL（cancel pending on shutdown） |
| #11 P0/P1 自主邊界 | PASS |
| #13 AI cost 感知 | PASS |
| #15 多 Agent 協作 | PASS |
| #16 組合風險 | CONDITIONAL（exposure 計算 verify） |
| #2/#10/#12/#14 | 不觸 |

### 13.2 9 條安全不變量

`authorization.json HMAC` INDIRECT touched — AC-9 + cancel pending on shutdown 覆蓋。其他 8 條無觸碰。

### 13.3 DOC-08 §12 合規

- §12.4 hard_stop 觸發 cancel + market re-submit 必 replay 驗 — `close_maker_race_tests.rs` Race A 場景覆蓋
- §12.9 不變量 — 9/9 PASS（FA verified）

---

## §14 IMPL 啟動 6 條件（v1.1 PM 規定，從 4 升 6 per AMD v0.2 §8）

**所有條件必滿足才能進 IMPL（強制工作鏈 PA→E1→E2→E4→QA→PM）**：

1. ✅ PA spec 完成（本文檔 v1.1）
2. ⏳ AMD-2026-05-15-02 v0.2 經 **QC + FA + BB + MIT 4-agent 並行 short re-review** 確認 17 must-fix + 14 should-fix 收口完整
3. ⏳ 三閘全過：
   - P0-EDGE-1 closed（[40] negative realized edge resolved）
   - W-AUDIT-8b Stage 0R passed（funding skew empirical evidence）
   - W-AUDIT-8a C1 BB/MIT sign-off（24h liquidation proof passed）
4. ⏳ IMPL 走強制工作鏈：PA spec finalize → E1 並行（A/B/C/D/E 5 worktree）→ E2 review → E4 regression → QA → PM sign-off。**不走 P0 快速通道**
5. ⏳ **F-FA-1 + F-FA-2 + F-FA-3 P1 finding pre-IMPL（v1.1 FA-MF-1）**：由 PA 在 IMPL kickoff 前 finalize 三 spec / verify
   - **F-FA-1**：V094 migration spec finalize（hybrid schema design + Linux PG dry-run × 2 round + sqlx checksum repair）— 預計 PA 1-day 出 spec
   - **F-FA-2**：portfolio_var exposure 計算 SoT 確認（maker pending 期間用 `request_qty` 不用 `filled_qty`）
   - **F-FA-3**：audit 欄位不走 spine lineage guard tests 設計（grep guard + integration test）
6. ⏳ **`reject_cooldown` entry/close 拆分升 P0 priority pre-Phase 2a Demo enable 必 land（v1.1 BB-MF-3）**：見 §6.1 詳述

---

## §15 後續工作項

| 項 | 負責 | 時點 |
|---|---|---|
| AMD-2026-05-15-02 draft | PM + PA | 立即 |
| 4-agent adversarial review on AMD | QC + FA + BB + MIT | AMD draft 完成後 |
| maker fill rate empirical baseline 查 | PA / E1 | 立即（不依賴 spec / AMD） |
| F-FA-1 V### migration spec（`trading.fills.details` audit 欄位） | PA | IMPL 前 |
| F-FA-2 portfolio_var exposure 計算 SoT 確認 | PA | IMPL 前 |
| F-FA-3 lineage contract guard（新 audit 欄位不走 spine） | PA | IMPL 前 |
| F-FA-4 partial maker close 對賬 SOP（DOC-08 §12 補章） | TW + FA | P2 後跟 |
| F-FA-5 `bb_mean_revert` 措辭修正（spec 内已修） | (已 done in §4.3) | — |
| MA KAMA fallback warn! + skip entry | E1 | W3-6 by-the-way scope-in（30 分鐘獨立修復） |
| phys_lock live 啟用決策 | operator + QC math | DEFER 至 Phase 2b 後另開 |
| **`P1-PORTFOLIO-RESTING-EXPOSURE-1`（v1.2 新增 per Wave 1 Track A3）** | **PA → E1** | **est. 3 person-day, 250 LOC；獨立平行 Phase 1b IMPL，互不阻塞**；fix `compute_correlated_exposure_pct` / `compute_exposure_pct` 在 `intent_processor/mod.rs:761-805` 把 `paper_state.resting_orders.qty` 加進 effective exposure 計算；解 entry-side resting maker 既有 systemic gap（per A3 verify report `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_2_portfolio_var_exposure_sot_verify.md` §8 fix scope）；對 close-maker-first 是「nice-to-have but not blocker」；派發時點：Wave 4+ |
| **`P2-ORDERS-INTENT-ID-WRITER-GAP-1`（v1.2 新增 per Wave 1 Track E3）** | **E1** | **est. 1 person-day**；fix `orders.intent_id` 100% NULL writer 漏接（per E3 finding 1）；恢復 intent → order linkage 給 Guardian-pass-rate 計算；不阻 Phase 1b IMPL；派發時點：N+2 backlog |

---

## §16 關鍵文件指針

- 改點：`srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:778-815 / 940 / 1123`
- 入場 maker 模板（反向 reuse）：`srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:77-177`
- IPC forward 已支援 Limit + PostOnly + maker_timeout：`srv/rust/openclaw_engine/src/event_consumer/dispatch.rs:504-538`
- Pending sweep（複用，無改動）：`srv/rust/openclaw_engine/src/event_consumer/pending_sweep.rs:53-76`
- maker rejection classify（擴展）：`srv/rust/openclaw_engine/src/strategies/maker_rejection.rs:43-72`
- phys_lock 4-gate 設計（未改）：`srv/rust/openclaw_engine/src/exit_features/v2.rs:286-288 / 351 / 174-180`
- entry maker 部署模式 SoT：`srv/docs/references/2026-04-24--postonly_design_intent.md`
- 配置：`srv/settings/strategy_params_{demo,live,paper}.toml`
- AMD 模板：`srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`

---

## §17 變更歷史

| 日期 | 版本 | 變更 | 作者 |
|---|---|---|---|
| 2026-05-15 | v1.0 | 初版（PM/PA/FA 3-agent verdict 整合）| Main session |
| 2026-05-15 | v1.1 | 4-agent (QC+FA+BB+MIT) round-2 consolidated patch — 17 must-fix（4 consensus + 13 unique）+ 14 should-fix 全 integrated；§1.2 fee saving 4.5→3.5 bps + net 推導；§4.3 phys_lock_gate4_giveback timeout 30→15s + buffer 2→1 + spread guard + small-tick；§4.4 V094 hybrid schema explicit + enum allowlist + Linux PG dry-run + non-training invariant；§5.4 dynamic backoff per-symbol → conditional global；§6.1 reject_cooldown 升 P0 prereq；§6.2 classifier reuse entry enum + side flag（不新建 Close*Variant）；§8.1 Wilson CI + sample-size + NULL ladder + reject sample healthcheck；§9.2 +4 新 test；§11 AC-1..AC-13 連續 + AC-14/15/16/17 4-agent must-fix；§14 IMPL prereq 4→6 條件；§15 後續工作項對齊 | PA per main-session 派 Wave 1 Track A1 |
| 2026-05-15 | v1.2 | A3+E3 finding consolidated（fee saving revision + race fallback gap + 14d pilot + P1+P2 ticket open）— §1.2 fee saving 3.5/+0.65 bps → 0.5-2.0 bps net per close attempt（per E3 empirical 0.66/0.95/3.31 三層解讀，引 E3 report path）+ 全年估 $160-$400 → $50-$200；§1.2 加 E3 三個意外發現（orders.intent_id NULL / orders.status fire-and-forget / 無 fallback to taker）；§5.5 NEW Race E mandatory fallback to taker（IMPL gate + 3 unit test + healthcheck [62] sub-check）；§10.1 Phase 2a 7d → 14d (7d primary + 7d extended observation)；§11.7 NEW AC-18 close_maker_fallback_to_taker_rate ≥ 95% + AC-19 14d close_maker_fill_rate ≥ 30%；§12.1 risk table 新 row HIGH「Close maker fallback 直接放棄 inherit entry-side gap」；§15 NEW `P1-PORTFOLIO-RESTING-EXPOSURE-1`（PA → E1，3 person-day，平行 Phase 1b）+ `P2-ORDERS-INTENT-ID-WRITER-GAP-1`（E1，1 person-day，N+2 backlog）| PA per main-session 派 Wave 1.5 (post-Track A3+E3) |
| 2026-05-15 | v1.3 | Wave 3a 4-agent re-review consolidation（QC + FA + BB + MIT verdict 4/4 APPROVED；QC 1 NEW MUST-FIX QC-MF-3 + 1 NEW SHOULD-FIX QC-SF-6；MIT 2 P3 advisory；A3 §12.2 framing 微調）— §11 開頭加 v1.3 patch footnote × 2（QC-MF-3 + QC-SF-6 邏輯）；**§11.1 AC-5** +1.5 → **+0.5 bps for n≥50 cells / directional only (≥ 0) for n<30 cells** (per QC-MF-3，對齊 §1.2 conservative range 下界；原 +1.5 與 §1.2 0.95 中性矛盾)；**§11.3 AC-11** +1.5 → **+0.5 bps** (per QC-MF-3，對齊 §1.2 下界)；**§11.7 AC-18** 補 Wilson-CI sub-clause（per QC-SF-6，CI lower < 90% → WARN，CI lower < 85% → FAIL，mirror AC-14 mechanism）；§5.5 line 410-411 加 footnote 引用 IMPL phase healthcheck [62] sub-check SQL Wilson 計算；§12.2 line 758 framing「組合風險 maker pending under-estimate」改「entry-side resting maker pending 期 portfolio under-estimate（既有 systemic gap，新 P1 ticket option A 平行解；close path is_reducing→allow() 不觸 portfolio gate 不引入新 risk vector）」（per QC §7 反問 5 衍生 + Wave 1 Track A3 verify 結論）；MIT-AC-19-Stratification-NOTE per-strategy + per-symbol 建議 OPTIONAL deferred IMPL phase healthcheck（不入 spec text，避免 over-spec）| PA per main-session 派 Wave 1.5b (Wave 3a re-review consolidation) |

**Sign-off Status**（v1.3 更新）：
- PM: APPROVED-CONDITIONAL（6 條件 + 6 governance gates；v1.3 純 numerical / cosmetic patch 不改條件數量，僅修 AC 數值 + framing）
- PA: READY-FOR-SPEC（A3 portfolio_var verify ✅ MAINTAIN + P1 ticket option A PM 預批；A4 W-C Caveat 2 guard tests + V094 兩段式 + writer gap explicit ✅；E3 maker fill empirical baseline ✅；Wave 3a 4-agent re-review consolidation ✅）
- FA round-1: APPROVED-CONDITIONAL（5 conditions）
- 4-agent round-2 consolidated: 4/4 APPROVED-CONDITIONAL（17 must-fix + 14 should-fix integrated 進 v1.1 + AMD v0.2）
- Wave 3a 4-agent short re-review on AMD v0.3 + spec v1.2: 4/4 verdict — QC APPROVED-CONDITIONAL (1 NEW MUST + 1 NEW SHOULD) / FA APPROVED (4 cosmetic) / BB APPROVED (per `2026-05-15--amd_v0_3_spec_v1_2_bb_short_re_review.md`) / MIT APPROVED (2 P3 advisory)
- Wave 1.5b v1.3 + AMD v0.4 patch: ✅ DONE (本次)；IMPL prereq 條件 2 SATISFIED

**下一步**：IMPL prereq 條件 2 解 → 等三閘（P0-EDGE-1 / W-AUDIT-8b / W-AUDIT-8a C1）+ 條件 6 reject_cooldown split (Wave 2b E1 in progress) + 條件 5 全 RESOLVED → Wave 3b BB 字典 6 處 + Wave 3.5 Linux V81/V91/V92/V93 backlog migration apply → IMPL kickoff Wave 4 (PA finalize IMPL plan → E1 5-worktree).
