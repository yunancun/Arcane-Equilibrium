# Dust-Frozen 持倉手動清理程序
# Dust-Frozen Position Manual Clear Procedure

**建立日期：** 2026-04-20
**觸發：** demo ENJUSDT 卡 🔴 塵埃凍結 / DUST，平倉按鈕無效
**關聯：** DUST-EVICTION-GAP-1 / P1-8（commit `51183ca`，2026-04-17）
**適用範圍：** demo / LiveDemo / Mainnet（live 前必清）

---

## 一、為什麼平倉按鈕按不動（背景）

引擎端 `paper_state/dust_gate.rs` 在 startup triage + per-tick retriage 都會對既有倉位做 `est_notional = qty * ref_price` 檢查：

| 條件 | 動作 |
|---|---|
| `est_notional >= min_notional` | 正常路徑（策略接管 / 或 evict 派平倉） |
| `est_notional < min_notional` | **凍結**為 `DUST_FROZEN_STRATEGY`（= GUI 顯示 🔴 塵埃凍結），**不派任何平倉訂單** |

原因：
1. Bybit min_notional gate 會直接拒絕 `est_notional < min` 的訂單（retCode 110094 / 110034）
2. 引擎若硬派單 → noise log + 風險決策被干擾（假 rejection 混入真 rejection）
3. 設計契約（`dust_gate.rs:39`）：
   > Operator must clear on Bybit GUI before going truly live.

**所以 GUI 按鈕「按了沒反應」= 正常 fail-closed，不是 bug。**

---

## 二、判別一個倉位是否為 dust-frozen

### 2.1 GUI 直接看
- Live/Demo tab 持倉卡片顯示 🔴 塵埃凍結 / DUST tag → 就是
- 可調參數：`owner_strategy = orphan_frozen`（= `DUST_FROZEN_STRATEGY` 常量）

### 2.2 從 engine.log 確認
```bash
grep "DUST-EVICTION-GAP-1" /tmp/openclaw/engine.log | grep -i "<symbol>"
```

典型 log：
```
DUST-EVICTION-GAP-1: bybit_sync position frozen
  kind=demo symbol=ENJUSDT is_long=true qty=0.1
  est_notional=0.0063 min_notional=5.0
```

### 2.3 Postgres 查所有當前 dust
```bash
PGPASSWORD=<pw> psql -h 127.0.0.1 -U trading_admin -d trading_ai -c "
SELECT symbol, engine_mode, qty, entry_price, qty*entry_price AS notional
FROM trading.positions_snapshot
WHERE owner_strategy = 'orphan_frozen'
ORDER BY engine_mode, symbol;"
```

（表名以實際 schema 為準；也可直接讀 `/tmp/openclaw/demo_state.json` / `paper_state.json` / `live_state.json` 的 positions dict，過濾 `owner_strategy="orphan_frozen"`）

---

## 三、清理路線（按環境）

### 3.1 Demo 環境（最常見、最無風險）

**路線 A — Bybit Demo Testnet GUI 手動平**（推薦）

1. 登入 https://demo.bybit.com
2. 用 OpenClaw demo API key 對應帳號
3. Derivatives → USDT Perpetual → Positions 頁
4. 找到目標 symbol（e.g. ENJUSDT）
5. 點 "Close" 按鈕 → 確認
6. Bybit GUI 對 native 持倉**不走外部 API min_notional gate**，允許 qty 平到 0
7. WS position event 傳回 engine → paper_state 自動同步移除 → GUI 紅標消失

**預期時序**：GUI 平倉 → 1-3 秒內 engine.log 出現 position WS update → 5-10 秒內 OpenClaw GUI 紅標消失

**驗證**：
```bash
grep "position.*ENJUSDT" /tmp/openclaw/engine.log | tail -5
# 應看到 qty=0 或 position removed
```

---

### 3.2 LiveDemo 環境

**與 Demo 同路線**，但登入 `api-demo.bybit.com` 對應的 demo 環境 GUI（LiveDemo 用 demo endpoint，帳號與 Demo 一致）。

額外注意：
- LiveDemo 是 **Live 管線走 demo endpoint**（feedback memory: live_no_degradation_by_endpoint）
- 清理前確認該倉位不在真實 live 管線的策略持倉內（若策略當前持有，先讓策略自己平）
- 清完再跑：`python3 helper_scripts/db/phase1a_c_readiness.py --engine-mode live_demo` 確認資料未受影響

---

### 3.3 Mainnet（真實資金，Live）

⚠️ **上 Live 前必須清光所有 dust_frozen**（見 §四 pre-live checklist）

**路線 A — Bybit Mainnet GUI 手動平**

1. 登入 https://www.bybit.com
2. 用 mainnet API key 對應的主帳號
3. Derivatives → Positions
4. 同 demo 操作

**路線 B — Bybit "Zero Dust" 一鍵清掃功能**（若該 symbol 支援）

Bybit 部分 spot / derivatives 有自動 dust sweep（< $1 自動兌換 BIT / USDT）：
- Spot Assets → Dust Balance → Convert
- 注意：僅 spot，perpetual positions 需手動

**路線 C — 加倉補足後平**（**強烈不建議**）

從 $0.006 補到 ≥$5 要加 ~790× qty：
- 成本：新加倉位 $5 本金 + funding fee + spread loss
- 風險：新加那段曝險可能反向虧損
- 結論：除非 dust 是歷史遺留且值 > $1，否則不值得

---

## 四、上 Live 前 pre-flight checklist

真實 live spawn 前，operator 必須：

```bash
# 1. 檢查 mainnet / live 環境無 dust_frozen
grep "DUST-EVICTION-GAP-1" /tmp/openclaw/engine.log | grep "kind=live" | tail -5
# 應為空

# 2. 確認 live_state.json 無 owner_strategy="orphan_frozen"
python3 -c "
import json
s = json.load(open('/tmp/openclaw/live_state.json'))
frozen = [p for p in s.get('positions', {}).values() if p.get('owner_strategy') == 'orphan_frozen']
print(f'Live dust-frozen count: {len(frozen)}')
for p in frozen: print(f'  {p[\"symbol\"]} qty={p[\"qty\"]} notional={p[\"qty\"]*p[\"entry_price\"]:.4f}')
"
# 應為 0
```

若有殘留 → 走 §3.3 Mainnet GUI 手動平 → 重啟 engine → 再驗一次。

---

## 五、為什麼不自動化這條路徑

Claude / Conductor 經評估後**決定不自動化**，理由：

1. **交易所 API 無「強制零倉」接口** — 任何自動化都只能派 reduce-only 訂單，同樣被 min_notional gate 擋住
2. **Bybit GUI 的特殊允許是客戶端 UX 特性** — 非 REST API 能呼叫，無法程式化
3. **dust 出現頻率低** — 通常是 Bybit auto-adjustment / partial-fill rounding / 歷史遺留，非常態路徑
4. **自動補倉風險 > 收益** — 見 §3.3 路線 C

⇒ 保持 fail-closed + operator manual 清理 的設計契約最穩。

---

## 六、歷史記錄

| 日期 | 事件 | 解法 |
|---|---|---|
| 2026-04-17 | P1-8 DUST-EVICTION-GAP-1 E1/E4 落地（commit `51183ca`）：triage 預檢 + orphan_frozen 分支 | 設計文件建立 |
| 2026-04-17 | P1-8 FUP：tick-level `retriage_synthetic_owner` 覆蓋所有 synthetic labels | 自動化 promotion 路徑（notional 回升時自動升級） |
| 2026-04-20 | demo ENJUSDT 卡 dust（qty=0.1 / notional=$0.0063） | 本文件記錄 — 待 operator 走 §3.1 路線 A 清理 |

---

## 七、相關代碼指針

- 設計契約：`rust/openclaw_engine/src/paper_state/dust_gate.rs`
- Tick-level retriage：`rust/openclaw_engine/src/paper_state/owner_attribution.rs:97-160`
- On-tick 入口：`rust/openclaw_engine/src/tick_pipeline/mod.rs:1939-2054`
- 常量定義：`rust/openclaw_engine/src/position_reconciler/orphan_handler.rs`
  - `DUST_FROZEN_STRATEGY = "orphan_frozen"`
  - `ORPHAN_CLOSE_DEDUP_MS`
