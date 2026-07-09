# PA pre-verify — ma_crossover BILLUSDT scope (D+1 PM SOP §1.2 Tier 1 #5 預驗)

**Date**: 2026-05-10
**Owner**: PA
**Trigger**: PM N+0 sign-off draft 6h spot check 揭露 ma_crossover 6h post-restart 4 fill 全 BILLUSDT (demo 2 + live_demo 2) — 是否 scope drift？
**Verdict**: **Case A** — ma_crossover scope **包**括 BILLUSDT (per-strategy blocklist 明確不含)；非 bug；維持觀察 + W5 P1-DYNAMIC-UNBLOCK-CHECK-1 spec 將自動承接 30d 證據評估
**D+1 SOP**: 本 task 已預驗，D+1 EOD spot check 不需重做 ma_crossover BILLUSDT 確認

---

## 0. TL;DR

ma_crossover 於 2026-05-07 至 2026-05-10 對 BILLUSDT 執行 16 次 fill (10 demo + 6 live_demo)，組成 8 個 round-trip。**符合設計範圍**（ma_crossover 的 blocked_symbols 在 risk_config*.toml 與 strategy_blocked_symbols_freeze.json 一致，名單為 NAORISUSDT / PENGUUSDT / FARTCOINUSDT / LABUSDT，**不含** BILLUSDT）。

8 個 round-trip 計算後：demo gross +0.45 USDT / 費用吃光至約 -0.075 USDT；live_demo gross +0.48 / 費用低 maker entry → +0.346 USDT；**combined net ≈ +0.27 USDT**，無明顯系統性負 edge 訊號（n=8 round-trip 過小，無法統計 freeze 觸發）。

QC W6 RFC §3 提到的 grid_trading BILLUSDT n=11 avg=-49.67 bps frozen — **僅適用於 grid_trading**（cluster severe-end + grid 結構性錯配）；不可直接傳遞到 ma_crossover 為 trade-eligibility decision (alpha sources 不同)。

---

## 1. Frozen Symbol List 結構

**SoT**: `srv/docs/governance_dev/strategy_blocked_symbols_freeze.json`（freeze_id `P2-AUDIT-VERIFY-5-2026-05-09`，scope=`new_entries_only`）

兩個獨立 per-strategy cell：

| 策略 | config_family | symbols 數 | BILLUSDT 在嗎？ |
|---|---|---|---|
| `grid_trading` | `settings/strategy_params_{paper,demo,live}.toml:grid_trading.blocked_symbols` | 17 | **YES**（last item） |
| `ma_crossover` | `settings/risk_control_rules/risk_config*.toml:per_strategy.ma_crossover.blocked_symbols` | 4 | **NO** |

**Runtime config triple-verify**（直接 grep 三 risk_config + freeze.json 無任何 (ma_crossover, BILLUSDT) 匹配）：
- `risk_config_demo.toml:52-61` `[per_strategy.ma_crossover]` `blocked_symbols = ["NAORISUSDT", "PENGUUSDT", "FARTCOINUSDT", "LABUSDT"]`
- `risk_config_live.toml:69-78` 同
- `risk_config_paper.toml` 同（4 env 都有，per memory `feedback_env_config_independence`）
- `risk_config.toml`（base）同（W-AUDIT-6 source-closed 後維持）
- 無其他 `ma_crossover.symbols` whitelist；ma_crossover 走 dynamic universe（whatever Scout 派 + 通過 universal blocked_symbols）

**結論**：BILLUSDT 在 ma_crossover trade-eligible scope 內 = **YES**（per-strategy ban 不含）；只在 grid_trading 被 freeze。

---

## 2. ma_crossover BILLUSDT 歷史 fill (全期 Linux PG 直查)

**Query**: `trading.fills WHERE strategy_name='ma_crossover' AND symbol='BILLUSDT'`

| engine_mode | n | first_ts (UTC) | last_ts (UTC) |
|---|---:|---|---|
| demo | 10 | 2026-05-07 14:22:00.295 | 2026-05-10 14:38:02.07 |
| live_demo | 6 | 2026-05-07 14:22:00.295 | 2026-05-10 14:41:15.53 |

**16 fill，4 day cumulative，今日 6h post-restart 4 fill = 2 round-trip**。

**Round-trip 計算 (manual)**：

| ts (UTC) | env | side seq | gross USDT | fee USDT | net USDT | exit_reason |
|---|---|---|---:|---:|---:|---|
| 14:22 → 14:22+30s | demo | Sell→Buy | -0.0756 | 0.0979 | **-0.1735** | phys_lock_gate4_giveback |
| 14:22 → 15:00 (38min) | live_demo | Sell→Buy | -0.4522 | 0.0448 | **-0.4970** | ma_reverse_cross |
| 00:56 → 00:56+31s | demo | Sell→Buy | +0.6262 | 0.1385 | **+0.4877** | phys_lock_gate4_giveback |
| 06:38 → 06:38+30s | demo | Buy→Sell | -0.2112 | 0.0963 | **-0.3075** | phys_lock_gate4_giveback |
| 16:10 → 16:11 (1min) | demo | Buy→Sell | +0.4959 | 0.0973 | **+0.3986** | TRAILING STOP |
| 16:10 → 16:11 (1min) | live_demo | Buy→Sell | +0.6214 | 0.0448 | **+0.5766** | TRAILING STOP |
| **14:35 → 14:38 (3min)** | demo | Buy→Sell | -0.3850 | 0.0956 | **-0.4806** | DYNAMIC STOP regime=trending atr=0.37 |
| **14:35 → 14:41 (6min)** | live_demo | Buy→Sell | +0.3105 | 0.0445 | **+0.2660** | TRAILING STOP |

(粗體 = 今日 6h post-restart 兩 round-trip)

**Aggregated**：
- demo (n=5 round-trip): gross +0.4503 fee 0.5256 → **net = -0.0753 USDT**
- live_demo (n=3 round-trip): gross +0.4797 fee 0.1341 → **net = +0.3456 USDT**
- **Combined net = +0.2703 USDT** (n=8 round-trip)

**Notional 估算**：BILLUSDT 0.01-0.02 USD/unit，single trade qty 1000-3000 unit → notional ≈ $20-60 → 0.5 USDT pnl ≈ 80-250 bps（極寬區間 due to 低絕對價格 noise）。

---

## 3. QC W6 RFC §3 cluster benchmark 對比解析

QC W6 RFC §3 grid_trading BILLUSDT n=11 avg=-49.67 bps frozen — 此 verdict 屬於 grid_trading 結構性錯配 cluster（grid 在 BILLUSDT 0.01 級價格 + low absolute spread 上 mean-reversion 假設不成立）。

**不可直接套到 ma_crossover** 的三個技術理由：

1. **Alpha source 不同**：grid 走 mean-reversion (limit order 在 grid 階梯)；ma 走 trend-following (KAMA cross + ADX>25)。同 symbol 不同 alpha 結構 = 獨立樣本，不能合併 cluster verdict。
2. **Sample 體量不對齊**：ma_crossover n=8 round-trip vs grid n=11+ exit-confirmed cycle，前者 0 freeze 觸發資格（per W5 spec 30d gate，需 fills>=80 + DSR/PBO + counterfactual）。
3. **Direction 對齊度不同**：ma 4 day 8 round-trip 中 4 winning round-trip 都是 trailing exit (1-3min hold)，4 losing 全是 phys_lock_gate4_giveback / DYNAMIC STOP / ma_reverse_cross (持倉 30s-38min)；trailing exit pattern 在 BILLUSDT 工作反映 BILLUSDT 短期動量/趨勢可被 ma 捕捉。grid 在同 symbol 反而虧光 = 兩策略對 BILLUSDT 微結構反應不同。

**Verdict on cluster transfer**：QC W6 RFC §3 cluster verdict **僅適用於 grid_trading scope**；ma_crossover BILLUSDT 需獨立 30d evidence (W5 spec 將承接)。

---

## 4. Decision Tree → **Case A**（細分為 A-with-watch）

| Case | 條件 | 適用？ |
|---|---|---|
| A | scope 包 BILLUSDT + 4 fill outcome 待 24h backfill 後查 → 維持觀察 | **YES** |
| B | scope 包 BILLUSDT + 歷史明顯負 edge → 加 P2 ticket | NO（n=8 過小，combined net 微正） |
| C | scope 不包 BILLUSDT（應 frozen）→ bug | NO（per-strategy ban 明確不含） |

**最終 verdict**：**Case A — 維持觀察，無需新 P2 ticket**。理由：
1. ma_crossover BILLUSDT trade 在當前 governance scope 內合法（risk_config + freeze.json 對齊）
2. n=8 round-trip net +0.27 USDT 還沒有足夠 power 觸發負 edge freeze (需 30d 完整 sample + DSR/PBO + counterfactual)
3. W6 today 翻正 +8.75 bps 整體 + ma_crossover 小樣本 +0.27 USDT 不衝突；DYNAMIC STOP 1 損 (regime=trending) 反映 ma 可能在 strong trending 下被 dynamic stop 過早平 — 屬策略內參數調優題，不是 BILLUSDT 黑名單題
4. 6h post-restart 4 fill 都在 14:35-14:41 同窗（疑似同個趨勢段觸發 entry + 立即被 trailing/dynamic exit），屬一次性 burst 而非 hot loop（未見 P1-MA-CROSSOVER-DUPLICATE-INTENT pathological pattern；duplicate_position reject 0 in BILLUSDT 6h window — 若有 hot loop 應該大量 reject）

---

## 5. Side note — phys_lock_gate4_giveback 比例偏高

8 round-trip 中 3 個 (37.5%) 因 phys_lock_gate4_giveback 平倉（demo 全部）；這比 W6 整體均值高（W6 close_reason_code distribution 上 phys_lock_gate4_giveback 約 ~10-15% per W6-3a audit）。

**可能解釋**：BILLUSDT 0.01 級價格 + bps noise 極大 → physical micro-profit lock gate 4 (giveback threshold) 容易觸發。

**屬性**：
- **不是** ma_crossover BILLUSDT scope 問題（這是 phys_lock 算法 vs low-price symbol 互動）
- **與 W6-3 close_reason_code enum 治理同源**（W6-3 已 enum 化此 reason 入 close_other 上一級）
- **不開新 P2**：歸入 W-AUDIT-8a Phase B/C 觀察 (alpha surface 升級後重評)；或 Sprint N+2 W-AUDIT-9 graduated canary 細化觀察 BILLUSDT specific stage stats

---

## 6. 建議 (per task scope)

| 動作 | Verdict |
|---|---|
| 加 P1 ticket (Case C) | NO — scope 包，無 bug |
| 加 P2 ticket (Case B) | NO — n=8 過小，combined net 微正，無 freeze trigger |
| 維持觀察 (Case A) | **YES** — 配合 W5 P1-DYNAMIC-UNBLOCK-CHECK-1 spec 30d 完整評估 |
| D+1 PM SOP §1.2 Tier 1 #5 | **PRE-VERIFIED**, drop from D+1 list (見 §7) |

**承接機制**：Sprint N+1 W5 dispatch 已預備 P1-DYNAMIC-UNBLOCK-CHECK-1 spec (`2026-05-10--p1_dynamic_unblock_check_1_spec.md`) 將 reuse `blocked_symbols_7d_counterfactual.py` 改 30d 版自動評估 (a) 17 frozen grid cells 是否該 unblock (b) 新增疑似負 edge 是否該 freeze。當該 spec land 後，ma_crossover BILLUSDT 將自動納入 30d evaluation queue（無需新 manual P2 ticket）。

---

## 7. D+1 PM SOP §1.2 Tier 1 #5 update

**原 Tier 1 #5 task**：
> 6h spot check 4 fill 全 BILLUSDT — D+1 EOD verify ma_crossover BILLUSDT scope drift 是否 bug

**Pre-verified verdict (此報告)**：
- BILLUSDT 在 ma_crossover trade-eligible scope = **YES** (per `risk_config*.toml:per_strategy.ma_crossover.blocked_symbols` + `strategy_blocked_symbols_freeze.json`)
- 4 fill 6h burst = 2 round-trip (Buy→exit pair, demo + live_demo) = **legitimate trade activity** (no hot loop, no scope drift, no fake-success)
- 全期 16 fill / 8 round-trip / combined net +0.27 USDT = **no freeze trigger**

**Action**: D+1 EOD spot check **drop ma_crossover BILLUSDT scope verify**，改為 monitor 24h backfill 進來的 net_bps (via `[40]` MLDE 平面 attribution)，若 24h cumulative ma_crossover BILLUSDT avg_net_bps < -50 bps 才升 P2 freeze evaluation；否則持續每日 [40] update 自動承接，無需 manual D+1 task。

---

## 8. 副作用清單 (read-only audit, 無 IMPL 改動)

| 項 | 影響 | 措施 |
|---|---|---|
| risk_config*.toml | 0 改動 | 無 (read-only) |
| strategy_blocked_symbols_freeze.json | 0 改動 | 無 (read-only) |
| dispatch v3.7 | 0 改動 | 無 (此 task scope outside dispatch) |
| 業務 code | 0 改動 | 無 (PA spec/audit only) |
| 16 原則 + DOC-08 §12 9 不變式 + 硬邊界 5 項 | 全 0 觸碰 | 純 read-only audit + report |

---

## 9. Evidence Files

- **Frozen list SoT**: `srv/docs/governance_dev/strategy_blocked_symbols_freeze.json`
- **Per-strategy ban runtime**: `srv/settings/risk_control_rules/risk_config_{demo,live,paper}.toml:[per_strategy.ma_crossover]`
- **Strategy params (no symbols whitelist for ma_crossover)**: `srv/settings/strategy_params_{demo,live,paper}.toml:[ma_crossover]`
- **Runtime fill PG query** (Linux trade-core): `trading.fills WHERE strategy_name='ma_crossover' AND symbol='BILLUSDT'`
- **Sibling counterfactual evidence**: `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--p2_audit_verify_5_blocked_symbols_freeze.md`
- **Sibling root-cause hot-loop audit (negative-control reference)**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`
- **W5 spec auto-承接 mechanism**: `srv/docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md` (預備中)
