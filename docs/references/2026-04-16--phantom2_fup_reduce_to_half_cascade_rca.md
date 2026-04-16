# P0-5 PHANTOM-2-FUP — ReduceToHalf one-shot guard 跨 tick 失效 RCA

**日期**：2026-04-16
**狀態**：Spec 完成，未排期實作
**路徑**：`rust/openclaw_engine/src/tick_pipeline/on_tick.rs:151-228` + `rust/openclaw_engine/src/fast_track.rs`
**TODO**：P0-5（不阻塞主關鍵路徑）

---

## 1. 症狀

P0-4 R1（`strategy_close:*` tag 透傳）部署後（baseline `2026-04-16 15:40:48 UTC`），認真核查 demo 引擎 2.6h 的平倉行為發現：

- `risk_close:fast_track_reduce_half` 累積 **335 筆**，vs `strategy_close:*` 合計 **42 筆** → 比例 **8:1**
- DB 1-min bucket 觀察到爆發模式：
  - `2026-04-16 16:29 UTC` 一分鐘 **130 fills** 跨 6 symbols
  - `2026-04-16 18:03 UTC` 一分鐘 **147 fills** 跨 7 symbols
- 引擎日誌 `18:03:41.602042Z → 18:03:41.603320Z`（**1.3 秒內**）：
  - **9 次 `FAST_TRACK ReduceToHalf` WARN 事件**
  - 全是 ORDIUSDT 觸發（`held_drop_pct=6.07%`、`held_drop_sigma=3.02`、`positions=2`、`risk_level=Cautious`）
  - 每次都印 "halving positions (one-shot)" — 但實際上每秒重複數次

ORDIUSDT 在這段內走 11 筆 `risk_close:fast_track_reduce_half` fills，部分 qty=0（執行端被 zero out）。

PHANTOM-2 fix（commit `348a9c5`，`worst_drop_for_held` + sigma 閘）已部署生效：`grep CloseAll engine.log` = **0**。CloseAll 路徑乾淨，問題只在 ReduceToHalf 路徑。

## 2. 根因

`tick_pipeline/on_tick.rs:151-163` 的 EDGE-P0-1 one-shot 重置邏輯**清空條件設得太寬**：

```rust
if self.governance.risk.level < openclaw_core::sm::risk_gov::RiskLevel::Defensive
    && !self.ft_reduced_symbols.is_empty()
{
    tracing::info!(cleared = self.ft_reduced_symbols.len(), "EDGE-P0-1: ...");
    self.ft_reduced_symbols.clear();
}
```

設計意圖（注釋寫的）：
> Once risk returns to Normal/Cautious/Reduced, positions can be halved again if a future Defensive episode occurs.

但 `evaluate_fast_track()`（`fast_track.rs`）在 risk_level **< Defensive** 時也會回 `ReduceToHalf`：

```rust
// 4. Moderate drop (≥5%) that is also a statistical outlier (≥3σ) on a held symbol:
//   - risk_level >= Defensive → CloseAll
//   - risk_level <  Defensive → ReduceToHalf (precaution, not panic)
```

→ 在 `risk_level=Cautious + held_drop≥5% + sigma≥3` 的條件下,每個 tick 走的循環是：

| 步驟 | 行為 |
|---|---|
| 1. tick N 進 on_tick | `evaluate_fast_track(Cautious, 6%, 3σ, ...)` → `ReduceToHalf` |
| 2. 行 155-163 | `risk < Defensive` 為真 → **清空** `ft_reduced_symbols` |
| 3. 行 175-228 | `ft_action == ReduceToHalf` 為真 → for-loop 對「不在集合裡」的 sym（**全部**）執行 emit_close_fill + execute_position_close + 標記入集 |
| 4. tick N+1（毫秒後） | 條件未變 → 同樣 `ReduceToHalf` → **再次清空** → **再次全 emit** |

→ Cautious + 5%+ drop + 3σ 持續存在期間，每 tick 重複 emit。 `ft_reduced_symbols` 集合**一直是空的**（每次進來先清，再 insert，下個 tick 開頭又清）→ "one-shot" 名存實亡。

證據對照：18:03:41 連續 9 次事件、`positions=2` 一致、`held_drop_pct` 6.0%~6.3% 微飄、`risk_level=Cautious` 不變 → 完全符合上述 loop 行為。

## 3. 為什麼 PHANTOM-2 fix 沒覆蓋這層

PHANTOM-2 修的是 `worst_drop_for_held` 的範圍問題（從掃全部 25+ symbols 縮到只看持倉），加 sigma 閘避免薄樣本誤觸 → 解決了 **CloseAll 全策略強平** 的最嚴重情境。

但 PHANTOM-2 fix **沒有觸碰** ReduceToHalf one-shot guard 的清空條件。實際上，`worst_drop_for_held` 縮小掃描範圍後，holds 裡的 ORDIUSDT 這類 6% 偏移 + 3σ 的真實 outlier，仍然合法觸發 ReduceToHalf — 而 guard 一直被清空，所以 ReduceToHalf 一直 emit。

## 4. 影響範圍

| 項目 | 影響 |
|---|---|
| **DB IO** | `trading.fills` 寫入量被 8x 放大，但每筆 fill 仍是 valid record（不破壞數據語義） |
| **engine.log 體積** | 2.6h 達 280MB；ReduceToHalf WARN 行佔比可觀 → 同 ENGINE-HEAL `engine_results.jsonl` 111GB 教訓的源頭模式 |
| **G-2 daemon 累積速率** | funding_arb 開倉後若觸發 6%+ 浮虧 + 3σ 偏移，在 Cautious risk 下會被 over-fast-track 持續半倉 → 阻止其走到自然 funding_arb_exit |
| **PnL 正確性** | `reduce_position()` 是部分平倉，本身仍正確；但 0-qty 雜訊 fill 大量寫入會混淆下游分析腳本 |
| **Phase 5 edge 評估** | risk_close vs strategy_close 比例失真，掩蓋策略真實 exit 表現（雖然 P0-3 評估用其他 6 策略而非依賴 funding_arb，但 ratio 噪音仍干擾） |

**未壞**：reduce_position 的會計正確；不會強平整倉；不破壞 governance 不變式。

## 5. 修復方案候選

### 方案 A：時間窗 cooldown（推薦）

```rust
// ft_reduced_symbols: HashMap<String, ts_ms>
const FT_REDUCE_COOLDOWN_MS: i64 = 60_000; // 60s 同 governance defensive episode 慣例

// 入場檢查（替換現行 .contains()）：
.filter(|p| {
    self.ft_reduced_symbols
        .get(&p.symbol)
        .map(|&last_ts| event.ts_ms - last_ts >= FT_REDUCE_COOLDOWN_MS)
        .unwrap_or(true)
})
```

**Why**：與 risk_level 解耦。同 symbol 60s 內只半倉一次，無關 governance 過渡。簡單、可測、行為可預期。

**清空時機**：可以保留 risk < Defensive 時清空作為快速復位（drop 結束後立刻允許新 episode），或完全移除清空邏輯讓 cooldown 自然過期。

### 方案 B：tick-level 整體 dedup（最保守）

```rust
let positions: Vec<...> = ...filter(|p| !ft_reduced_symbols.contains(&p.symbol)).collect();
if positions.is_empty() {
    return; // 全在 set 中，整體跳過
}
```

但此補丁不解決 set 被清空的根問題 — 仍會在 tick N 清空後 tick N+1 整個 list 再進來。需與 A 或 C 結合。

### 方案 C：收緊清空條件至 Normal

```rust
if self.governance.risk.level == openclaw_core::sm::risk_gov::RiskLevel::Normal
    && !self.ft_reduced_symbols.is_empty()
{
    self.ft_reduced_symbols.clear();
}
```

**Why**：only 完全恢復到 Normal 才清空，保留 Cautious/Reduced 狀態下的 one-shot 不變式。

**Why not 單用 C**：仍然依賴 governance 狀態做唯一信號。如果 governance 在 Cautious/Defensive/Cautious 反覆切換，Cautious 期間累積的 reduce 就永遠不會清 → 同 episode 結束後新的真實 drop 無法再半倉（保護過頭）。

### 推薦組合：A + C

- 主機制 A：60s cooldown 保證 burst 行為
- 副機制 C：完全 Normal 後清空，讓「真正復原 + 新 episode」場景能再次半倉

## 6. 為什麼不立刻動手

- 當前**未壞** — `reduce_position` 會計正確，不會強平整倉，不破壞 governance 不變式
- Phase 5 PAUSED 狀態下噪音不造成新傷害（`P0-3` 不依賴 funding_arb 子集）
- P0-0 RECONCILER-BURST-FIX（2026-04-16 已修復待部署）解掉啟動期 burst → Defensive 自動升級的源頭，會大幅減少 ReduceToHalf 觸發頻率，可能讓 P0-5 的觀察症狀變不明顯
- **建議流程**：P0-0 部署 → 觀察 24-48h ReduceToHalf cascade 是否仍存在 → 若仍見每秒多次 fire 才開動 P0-5 修復

## 7. 驗收

1. **單元測試**（`tick_pipeline/tests.rs`，擴充 L171 已有 fixture）：
   - `test_ft_reduce_to_half_one_shot_under_persistent_cautious`：餵 5 個連續 tick，risk=Cautious、held_drop=6%、sigma=3 不變 → 期望 emit_close_fill 只觸發 1 次（首 tick）
   - `test_ft_reduce_to_half_re_arms_after_cooldown`：cooldown 過期後同條件再次觸發 → emit 第 2 次
2. **行為觀察**（部署後）：
   - `grep "FAST_TRACK ReduceToHalf" /tmp/openclaw/engine.log | head -100` → 同 symbol 連續事件時間戳間隔 ≥60s（不再毫秒連發）
   - `risk_close:fast_track_reduce_half` 24h 計數 < 50（vs 當前 335/2.6h）
3. **回歸**：engine lib + reconciler_e2e 全綠

## 8. 接手指南

- **修改點**：
  - `rust/openclaw_engine/src/tick_pipeline/mod.rs:738`（型別 HashSet → HashMap）
  - `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:151-228`（清空條件 + filter 邏輯）
- **不動**：
  - `fast_track.rs evaluate_fast_track()`（規則本身正確；問題在 caller 的 guard）
  - `governance.risk_gov`（不破壞 fail-closed 不變式）
- **單測位置**：`tick_pipeline/tests.rs:171` 既有 ReduceToHalf fixture 可擴展
- **觀察手段**：
  ```bash
  grep "FAST_TRACK ReduceToHalf" /tmp/openclaw/engine.log | \
    awk -F'T' '{print substr($2,1,8)}' | uniq -c | sort -rn | head
  ```
- **相關 commit**：
  - `348a9c5`（PHANTOM-2 fix，是這次發現的前置）
  - `a5401ce`（P0-4 R1，揭露這個現象的 tag 透傳修復）

## 9. 預估

- spec 0.5d（本文件）✅
- 實作 0.5d（型別變更 + filter + 2-3 單測）
- 回歸 0.5d（engine lib + 端到端觀察）
- **總計：1.5d**

---

**作者**：Claude Code (CCAgent) — 認真核查 P0-4 R1 部署後行為時發現
**Reviewer**：待 PM 排期後 E3
