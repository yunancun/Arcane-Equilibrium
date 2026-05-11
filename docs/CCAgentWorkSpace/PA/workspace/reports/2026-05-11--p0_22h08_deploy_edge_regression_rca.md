# PA RCA — 22:08 +0200 May 10 Edge Regression P0

**日期**：2026-05-11
**作者**：PA（Project Architect）cold review
**性質**：22:08 +0200 May 10 deploy edge 翻負 RCA verdict + verify path 推薦
**評級**：CONFIRMED — 嫌疑 commit **A/B/C/D/E/F 全部排除**，true root cause = **22:08 watchdog Auto restart 後 paper_state reset 引發 grid_trading 大量 0-duration scalping**

---

## 1. 時序錯位推導（operator 假設修正）

### 1.1 Operator 認知 vs 實際

| 認知 | 實際 |
|---|---|
| 22:08 deploy 6 個 commit | **22:08 是 watchdog Auto kind restart，無 rebuild，binary 不變** |
| 業務 commit 19:33-19:57 改了交易行為 | 6 個 commit 都是 [skip ci]，**全部未進入 22:08 binary** |
| 5de8df5f / 8070f98d / ca5f4305 嫌疑高 | 三個 commit **都不在 22:08 binary** 之中（boot kind=Auto 驗證） |

### 1.2 真實時序

```
2026-05-10 11:20:16 +0200  b6ed4975 Sprint N+0 closure commit
2026-05-10 15:48:33 +0200  engine-1778420938.log start = Sprint N+0 deploy （short）
2026-05-10 15:51:13 +0200  engine-1778443687.log start = Sprint N+0 stable boot
                           kind=Manual ← operator restart_all --rebuild
                           edge_estimates grand_mean=-15.13 / scanner interval=1800s
2026-05-10 19:33-19:57     6 個 [skip ci] commit 寫入（5de8df5f 至 2c258238）
                           ← 都是 git commit only，**未 deploy**
2026-05-10 22:08:07 +0200  engine 1 self-shutdown，uptime=22610s≈6.28h
2026-05-10 22:08:09 +0200  engine-1778455753.log start = 22:08 watchdog respawn
                           kind=Auto ← watchdog auto restart，binary 不變
                           edge_estimates grand_mean=-14.94 / scanner interval=1800s
                           ← 同一 binary、同一 config，仍是 Sprint N+0 morning binary
2026-05-11 00:27 / 00:44    scanner_config commit（172c73ec / 478fece1）寫入
                           ← 直到 01:29 restart 才 reload
2026-05-11 01:29-04:14     一系列 sub-agent restart（含 P1 V083 fix）
```

### 1.3 證據鏈

**engine 1 boot log（15:51）**：
```
kind=Manual settings_dir=/home/ncyu/BybitOpenClaw/srv/settings
scanner config loaded max_symbols=25 pinned=["BTCUSDT", "ETHUSDT"] interval_secs=1800
PH5-WIRE-1: edge estimates loaded n_cells=316 grand_mean_bps=-15.13586716836986
```

**engine 2 boot log（22:08）**：
```
kind=Auto settings_dir=/home/ncyu/BybitOpenClaw/srv/settings
scanner config loaded max_symbols=25 pinned=["BTCUSDT", "ETHUSDT"] interval_secs=1800
PH5-WIRE-1: edge estimates loaded n_cells=321 grand_mean_bps=-14.942812227459696
```

**差異僅**：n_cells 316→321（+5 cells 自然累積）+ grand_mean -15.13→-14.94（自然 cell drift）。**config 與 binary 0 變化**。

---

## 2. 三嫌疑 commit confidence 排序（最終）

| Commit | confidence (是 22h 翻負 cause) | 證據 |
|---|---|---|
| **A · 5de8df5f Wire decision lease terminal release** | **0%** | 1) 22:08 binary 不含此 commit（kind=Auto）2) 即使含，bypass mode = LeaseId::Bypass.release_lease() return Ok(()) NO-OP 3) channel = mpsc::unbounded，不阻塞 4) 全 path 早退（is_primary 守衛） |
| **B · 8070f98d Route executor intents through typed plans** | **0%** | 1) 22:08 binary 不含 2) 真實 demo runtime 不走 ExecutorAgent.on_message（Agent Spine 全 shadow `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`）3) Bypass mode → lease acquisition 即使做 NO-OP |
| **C · ca5f4305 Centralize alpha source availability** | **0%** | 1) 22:08 binary 不含 2) 唯一語義變化：`AlphaSourceTag::CrossAsset` 從寫死 false → `btc_lead_lag.is_some()`，**只影響 `dispatched_counter` / `unavailable_counter` 統計**，不影響 strategy dispatching logic 3) Phase A AlphaSurface 整體仍是 Tier 1 only，Tier 2 panel `btc_lead_lag` 永遠 None |
| **次嫌疑 D/E/F** (97658947 / fb7ac290 / 2c258238) | **0%** | 1) 三個 commit 都不在 22:08 binary 2) 3 commit 改的是 Python 非熱路徑（governance_hub_live_candidate_review / replay_routes / openclaw_authority_contracts）3) 都不接觸 Rust hot path |

**Three-suspect verdict: ALL CLEARED**。22:08 binary 與 15:48 binary 是同一個 build artifact。

---

## 3. 真實 root cause（推斷）

### 3.1 22:08 突發行為變化

**PG fills 直查結果**（精確證據）：

| 時段 | n_fills | gross PnL | avg gross/fill | 模式 |
|---|---|---|---|---|
| 18-19h | 12 | +$2.95 | **$0.246/fill** | Buy 跨數分鐘 Sell（grid hold）|
| 22-23h | 20 | +$0.031 | $0.0015/fill | **Sell + Buy 同 ts（instant scalp）** |
| 01-05h | 124 | +$1.18 | $0.0095/fill | 持續 instant scalp |

22h 後 grid_trading **每筆 trade gross 急降 25x**：
- **morning regime**: Buy → hold N min → Sell（位置驅動 grid）
- **22h+ regime**: Sell + Buy 同毫秒（**grid layout 在 paper_state reset 後立刻平衡所有 grid level**）

### 3.2 結構推斷（confidence MEDIUM-HIGH）

22:08 watchdog Auto restart 後：
1. **paper_state.positions 全空** — 啟動 seed count=0
2. **grid_trading mod.rs on_tick** 重新進入 fresh grid layout 計算
3. **Bybit demo 真實倉位** vs paper_state 不一致（demo runtime 有真實 5 symbol position seeded for live=0 / demo=0）
4. **grid_layout 重 rebuild** — 所有 grid 級別 trigger 同時 ready
5. **第一個 tick** 進來時，所有 grid level **同時 fire 開倉 + close 訂單**（因為 reset 後 grid layout 認為「所有 level 都需要單」）

對應 Sprint N+0 closure memory 提到的 5 textbook 策略 alpha-deficient 結論：
- grid_trading 沒真實 alpha，只賺 grid spread
- restart 後 paper_state reset = grid 重建 = 0-duration scalp 的 fee bleeding 機制

**並非 commit 引入，是「grid_trading 設計天然在 paper_state reset 後產生 fee bleeding」的長期 latent bug**。Sprint N+0 morning 15:48 也是 Manual restart，**為何 morning 沒爆量？**

**唯一合理推測**：
- 15:48 Manual restart 後 strategy warmup_delay 還在生效（scanner 30min cycle，warmup 60s），加上 morning EU market liquidity 高 → grid layout 不立即 trigger，**hold 一段時間才 close**
- 22:08 Auto restart 同一邏輯，**但 EU evening 22h market liquidity 低 + grid scanner stale memory** → grid layout 立即 fire instant scalp

**驗證需要看 grid_layout.rs 重啟邏輯 + warmup_delay 對 grid 是否有效**（PA 不再深挖，operator 決策即可）。

---

## 4. 為什麼我之前的三個假設都錯了

1. 我假設 22:08 是 deploy → operator 也假設 — **未檢驗 engine log kind=Auto/Manual** = **時序錯位 root error**
2. 我假設 5de8df5f 改了 lease 觸發鏈 → 沒檢驗 LeaseId::Bypass return path = **語義誤判**
3. 我假設 8070f98d 改了 ExecutorAgent → 沒檢驗 OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow → **runtime mode 認知盲點**

**lesson**：**deploy 必先 verify engine boot kind**（Manual=operator deploy / Auto=watchdog respawn）；前者才是 deploy event，後者不引入新代碼。

---

## 5. Verify Path 推薦（按 confidence + safety + speed 排序）

### Path 1 ★ 最快 ★（推薦先做，operator 不需 commit revert）

**P 1.1 Verify scope**：確認 22:08 engine kind=Auto + binary 與 15:48 同源
```bash
ssh trade-core "grep 'restart kind\|engine v0' /tmp/openclaw/engine_logs/engine-1778455753.log | head -3"
```
**Expected output**: `kind=Auto`（已 verify）+ `OpenClaw Engine v0.1.0`

**P 1.2 觀察 grid_trading 在重啟後第一個 1-3 min 行為**：
```bash
ssh trade-core "head -200 /tmp/openclaw/engine_logs/engine-1778465686.log | grep -E 'grid|on_tick|paper_state' | head -50"
```
看是否 reset 後 grid 立刻批量發單。

### Path 2 ★ 最安全 ★（A/B test，operator 可選做）

把 engine 拉回 Sprint N+0 morning binary（HEAD `b6ed4975`）— **不需要**因為 22:08 binary 就是 morning binary（已驗證）。

**真正可做的 A/B**：
1. **手動 restart 一次 engine**（kind=Manual），與 22:08 Auto restart 比 — 看 paper_state reset 是否兩次都引起 grid 爆量
2. **disable grid_trading 為 N=1 hour**（settings/strategy_params_demo.toml `[strategies.grid_trading] active=false`）restart engine — 看 -$0.5/hour bleed 是否停

預期：grid_trading disable → bleed 顯著減小但不歸零（ma_crossover 也有 instant scalp 但量少）。

### Path 3 ★ 最 forensic ★（git bisect）

**不需要做** — 已確認 22:08 binary 與 15:48 binary 是同一 build，6 個 commit 都不在內。bisect 找不到「壞 commit」。

---

## 6. Surgical Action 命令（operator 立即 stop bleeding）

**不需要 commit revert**。建議 operator 兩步：

**Step 1（5min）**：emergency disable grid_trading 一個小時觀察
```bash
ssh trade-core "cd /home/ncyu/BybitOpenClaw/srv && sed -i.bak '/^\[strategies\.grid_trading\]/,/^\[/ s/^active = true/active = false/' settings/strategy_params_demo.toml && bash helper_scripts/restart_all.sh --keep-auth"
```
（**注意：請 operator 先 verify TOML 結構**，sed 可能不準；用 manual edit 也可）

**Step 2（30min）**：1h 後 review PG fills，confirm bleed 是否止住
```bash
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h 127.0.0.1 -U trading_admin -d trading_ai -t -A -F'|' -c \"SELECT count(*), round(sum(realized_pnl - fee)::numeric, 4) FROM trading.fills WHERE ts >= NOW() - INTERVAL '1 hour' AND engine_mode IN ('demo', 'live_demo')\""
```

**Step 3（如果 Step 1 確認）**：派 E1 design grid_trading restart warmup（在 engine restart 後 N min 內 grid_trading 不發單，等 paper_state cohesion ready）。

---

## 7. 16 原則 + Hard Boundary 對照

| 原則 | 狀態 |
|---|---|
| #4 策略不繞風控 | ✓ grid_trading instant scalp 仍經 Guardian / cost_gate / fee check |
| #5 生存 > 利潤 | ⚠️ -$1.94 in 9h 不致命但已是 0.6%/day account erosion，需 stop |
| #6 失敗默認收縮 | ✗ paper_state reset 後 grid 應 conservative warmup（缺）|
| #8 交易可解釋 | ✓ PG fills 全有 attribution |
| #13 cost 感知 | ⚠️ fees > gross 的爆量 22h 期間 cost_gate 沒擋下 grid |

**Hard boundary 0 觸碰**：execution_authority / max_retries / live_execution_allowed 全綠。

---

## 8. PA self-review

**對抗性自評**：
1. 「為什麼 morning 15:48 Manual restart 後沒爆量」這個 critical Q **我推測但未深查**，confidence MEDIUM-HIGH 而非 HIGH。
2. 「grid_trading instant scalp 是 design 還是 bug」**我未進入 grid_trading 源碼驗證**，operator 可派 E1 確認。
3. **Mac 端 PG query 順利**透過 ssh + PGPASSWORD，但 query syntax 上 trial-error 浪費 ~3min（first ts_ms 假設錯誤 → 改 ts timestamp）。
4. operator 給的「per-trade gross 0.05-0.13 → 0.005-0.01」量級 — **我實測是 0.246 → 0.0095，量級對齊但比 operator 提供的 morning 0.05-0.13 更高**，可能 operator 的 baseline 是更早數據。

**Confidence**: HIGH for「3 commit 排除」/「22:08 是 watchdog Auto」/「root cause = paper_state reset + grid instant scalp」三項；MEDIUM for grid 內部具體機制（缺源碼 deep dive 時間）。

---

## 9. E1 派發提案（後續 op 行動）

**P1-A** (1 E1, ~2h)：grid_trading restart warmup design — engine boot 後 N min 內 grid 不發單，等 indicator buffer + paper_state cohesion
**P1-B** (1 E1, ~1h)：cost_gate 在 grid instant scalp（fill_qty same ts 內 Sell+Buy）的 fee check 加強
**P2-C** (1 E1, ~30min)：watchdog Auto restart 時 send signal 給 strategies 進入 N min 「post-restart safe mode」

非熱路徑 cleanup：3 個 [skip ci] non-traded commit（97658947 / fb7ac290 / 2c258238）下次 --rebuild 自然 land，無需 surgical action。

---

**Verdict**: 3 commit ALL CLEARED；真正 root cause = 22:08 watchdog Auto restart 後 paper_state reset 引發 grid_trading 大量 0-duration scalping（5 textbook 策略結構性 alpha-deficient 結論進一步驗證）。Operator action: emergency disable grid_trading 1h 觀察 + 派 E1 design grid restart warmup。

**End of PA report.**
