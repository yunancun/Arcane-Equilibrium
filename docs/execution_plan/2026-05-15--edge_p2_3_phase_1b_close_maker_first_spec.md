# EDGE-P2-3 Phase 1b — Close-Maker-First Refactor Spec

**Date**: 2026-05-15
**Author**: PM + PA + FA convergent audit chain (main session)
**Status**: SPEC DRAFT — pending AMD-2026-05-15-02 governance review + 3-gate prereq
**Phase**: EDGE-P2-3 Phase 1b（entry-only Phase 1a 自然延伸到 close path 同 alpha 軸；1c 留 microstructure；P2-4 留 alpha source promotion gate）
**Supersedes**: 無；補完 EDGE-P2-3 Phase 1a entry-only scope-limiting 設計決策
**對應 spec / TODO**: P0-EDGE-1 / EDGE-P2-3 / W-AUDIT-8b (alpha-source 後續) / DOC-01 §5.6 § §5.9 / DOC-08 §12

**Source verdicts**:
- PM: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--close_maker_first_pm_verdict.md` — APPROVED-CONDITIONAL
- PA: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md` — READY-FOR-SPEC
- FA: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md` — APPROVED-CONDITIONAL

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

**保守估算**：每筆 close 從 taker (5.5 bps) → maker (≈1 bps) 節省 ~4.5 bps fee。
- live_demo grid 7d 155 active closes × 平均倉位 $300 × 4.5 bps ≈ **$2.1 / week / grid**
- 跨 5 策略 + 21 symbols 全年估 `~$200-$500 fee saving`
- **不能救 -110 USDT structural alpha deficit**（PM 判 P1，非 P0）
- 真正價值：消除執行成本掩蓋 alpha 信號，讓 P0-EDGE-1 edge measurement 更乾淨

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
| phys_lock_gate4_giveback | 2 | 1.0 | 30000 | profit lock，可稍偏好 |
| phys_lock_gate4_stale_roc_neg | 1 | 0.5 | 10000 | ROC<0 + stale 已偏弱，短 timeout |
| bw_squeeze / pctb_revert | 1 | 0.5 | 30000 | 樣本量低，conservative |

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

### 4.4 Audit 欄位（V### migration 配套）

新增到 `trading.fills.details` JSON（不破 V083 schema，向後兼容）：
```json
{
  "close_maker_attempt": true,
  "close_maker_fallback_reason": "timeout_taker | postonly_reject | cancel_grace_expired | ack_lost | not_attempted_safety_path",
  "close_initial_limit_price": 1234.56,
  "close_final_fill_price": 1234.50,
  "close_maker_eligible_reason": "grid_close_short"
}
```

對應 V### migration（PA 後續開 P1-FILLS-MAKER-CLOSE-AUDIT）負責 schema 升級 + healthcheck check_close_maker_fill_rate。

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

### 5.4 Race D：reject `TooManyPending`

**情境**：rate limit 觸發。

**規則**：
1. 直接 market 完成本筆 close
2. **全域 close maker pause 5 分鐘**（避免 rate limit 雪崩）
3. 寫 audit row：`close_maker_fallback_reason = "rate_limit_pause"`

---

## §6 Reject + Cooldown 處理

### 6.1 cooldown 拆分（修現存 bug）

| 欄位 | 用途 | 值 |
|---|---|---|
| `reject_cooldown_entry_until_ms` | entry maker reject cooldown | 沿用既有邏輯 |
| `reject_cooldown_close_until_ms` | close maker reject cooldown | 新增；TooManyPending → 5min，其他 → 1min |

### 6.2 maker_rejection.rs 擴展

`MakerRejectionCategory` 枚舉已存在；close side 加入：
- `Self::CloseTooManyPending` → 觸發 5min global close maker pause
- `Self::ClosePostOnlyCross` → 立即 market，不進 cooldown
- 其他既有變體 close 路徑沿用 entry side 處理

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

### 8.1 新增 passive_wait_healthcheck

```python
def check_close_maker_fill_rate():
    """
    [62] close_maker_fill_rate — Phase 1b 部署後 PASS gate
    PASS: 7d close maker fill rate ≥ 60% (mirror entry [3])
    WARN: < 60% but ≥ 40%
    FAIL: < 40%
    """
```

```python
def check_close_maker_fallback_audit():
    """
    [63] close_maker_fallback_audit — audit 完整性
    PASS: 100% close fills 有 close_maker_attempt + close_maker_fallback_reason
    FAIL: 任何 NULL
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

---

## §9 Test 影響面

### 9.1 既有測試

PA grep 確認受影響 reason-string assert（**reason 字串不變不破**）：
- `grid_trading/tests.rs` 4 處
- `ma_crossover/tests.rs` 3 處
- `bb_reversion/tests.rs` 2 處
- `bb_breakout/tests.rs` 1 處

合計 10 處，reason 字串保留，**無 breakage 風險**。

### 9.2 新增測試

| 測試 | 文件 | 覆蓋 |
|---|---|---|
| Whitelist classifier unit | `commands_close_maker_tests.rs` | 8 maker + N market 全 case |
| compute_close_limit_price unit | `common/maker_price_close_tests.rs` | strict-skip / per-reason buffer / inverted is_long |
| State machine 4 race integration | `tick_pipeline/close_maker_race_tests.rs` | A/B/C/D 各場景 |
| cooldown 拆分 regression | `event_consumer/cooldown_isolation_tests.rs` | entry reject 不影響 close path |
| Sweep close maker reuse | `event_consumer/pending_sweep_close_tests.rs` | timeout fallback to market |
| Rollback kill-switch | `commands_close_maker_rollback_tests.rs` | TOML flag flip → 1 tick 內 market |
| Audit field non-null | `database/fills_audit_close_maker_tests.rs` | 100% 寫入完整性 |

E1 估計：~400 LOC tests。

---

## §10 Rollout — demo → live_demo → live

### 10.1 三段灰度（mirror EDGE-P2-3 Phase 1a entry 模式）

| 階段 | 期間 | 環境 | 啟用方式 |
|---|---|---|---|
| Phase 2a Demo | 7d | demo | TOML `use_maker_close=true` / per-策略獨立 flag |
| Phase 2b LiveDemo | 7d (Phase 2a PASS 後) | live_demo | TOML override per-策略 |
| Phase 3 Live | indefinite | live (Mainnet) | **operator 顯式 sign-off** + AMD 補件 |

### 10.2 Kill-switch

| 觸發 | 動作 |
|---|---|
| TOML hot-reload `use_maker_close=false` | ArcSwap 1 tick 內回 market |
| `close_maker_fail_rate > 50% over 5min` | IPC `/operator/risk/exit_patch` 自動 disable + alert |
| Engine shutdown / authorization 失效 | cancel_token 觸發 best-effort cancel pending |

---

## §11 Per-stage PASS Criteria

### 11.1 Phase 2a Demo PASS（最早 2026-05-29+ 7d 觀察）

| AC | 內容 |
|---|---|
| AC-1 | demo close maker 比例 ≥ 60% |
| AC-2 | fallback (maker_timeout → taker market) 比例 ≤ 30% |
| AC-3 | `close_dispatch_failed` counter 不增 |
| AC-4 | per-strategy 5 close exit_reason 各自 close fill ≥ 10 條（bw_squeeze/pctb_revert 各 ≥ 1，套 §4.3 carve-out gate） |
| AC-5 | close 平均 net_bps（fee net）改善 ≥ taker baseline 的 +3 bps |
| AC-6 | `trading.fills.details` 中 `close_maker_*` 100% non-null |
| AC-7 | 健康檢查 `[62][63]` PASS 7d 持續 |

### 11.2 Phase 2b LiveDemo PASS（再 7d）

| AC | 內容 |
|---|---|
| AC-8 | LiveDemo Phase 2a 同等指標滿足 |
| AC-9 | authorization.json HMAC re-verify 期間 0 stray pending maker close orders |
| AC-10 | MAG-082/083/084 全 ✅ 維持，無 regression（W-C lease lineage 寫入正常） |

### 11.3 Phase 3 Live（Mainnet only）

| AC | 內容 |
|---|---|
| AC-11 | Phase 2b 14d 內 0 P0 regression + close net_bps Δ vs Phase 1a baseline ≥ +5 bps |
| AC-12 | operator 顯式 sign-off |
| AC-13 | AMD 補件（live carve-out + 翻 flag posture） |

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

### 12.2 FA 識別的功能 / 合規 risk

| Risk | 等級 | Mitigation |
|---|---|---|
| §二 #5 生存 > 利潤 maker timeout 期 expose 風險 | CONDITIONAL | `phys_lock_gate4_stale_roc_neg` timeout 降到 10s；AC-2 fallback ≤30%；AC 必含 close_timeout_pre_stopout_rate ≤ 5% |
| §二 #6 失敗默認收縮 | CONDITIONAL | cold-boot=false / live 預設不啟用 / 三段灰度 |
| §二 #8 交易可解釋 | CONDITIONAL | 新欄位 V### migration（F-FA-1 P1） |
| §二 #9 災難保護 pending maker on shutdown | CONDITIONAL | cancel_token 路徑 cancel_resting_maker_order best-effort；authorization 失效 → 清 pending |
| §二 #16 組合風險 maker pending 期 portfolio under-estimate | CONDITIONAL | request_qty vs filled_qty exposure 計算（F-FA-2 verify） |

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

## §14 IMPL 啟動 4 條件（PM 規定）

**所有條件必滿足才能進 IMPL（強制工作鏈 PA→E1→E2→E4→QA→PM）**：

1. ✅ PA spec 完成（本文檔）
2. ⏳ AMD-2026-05-15-02 draft 完成（次步） + 經 **QC + FA + BB + MIT 4-agent 並行 adversarial review**
3. ⏳ 三閘全過：
   - P0-EDGE-1 closed（[40] negative realized edge resolved）
   - W-AUDIT-8b Stage 0R passed（funding skew empirical evidence）
   - W-AUDIT-8a C1 BB/MIT sign-off（24h liquidation proof passed）
4. ⏳ IMPL 走強制工作鏈：PA spec finalize → E1 並行（A/B/C/D/E 5 worktree）→ E2 review → E4 regression → QA → PM sign-off。**不走 P0 快速通道**

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

**Sign-off Status**：
- PM: APPROVED-CONDITIONAL（4 條件 + 6 governance gates）
- PA: READY-FOR-SPEC（1 NEEDS-PROBE on rate-limit；0 BLOCKED-BY-1B-4.2）
- FA: APPROVED-CONDITIONAL（5 conditions）

**下一步**：寫 AMD-2026-05-15-02 → 派 QC+FA+BB+MIT 4-agent 並行 adversarial review → 等三閘（P0-EDGE-1 / W-AUDIT-8b / W-AUDIT-8a C1）→ IMPL 工作鏈啟動。
