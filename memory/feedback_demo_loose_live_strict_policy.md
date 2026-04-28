# Demo 放寬 / Live 收緊 政策（2026-04-28 EDGE-DIAG-2 確立）

## 核心原則

**Demo 環境的權限可以適量放寬，Live（含 LiveDemo）需要收緊** — 即便兩者跑同一份 engine binary。背後邏輯：

1. **Demo 是學習資料源**（per `feedback_demo_over_paper_for_edge.md`）— edge 估計、參數調校、agent / ML 訓練資料都從 demo fills 累積。如果 demo 路徑被過度保守的 gate 卡住，learning pipeline 會結構性饑餓。
2. **Live 對應真實資金 + 真實 ToS 風險** — 任何不確定都該 fail-closed（CLAUDE.md §二 原則 #5「生存>利潤」）。
3. **核心是「平衡虧損與盈利」，不是「一味保守」** — operator 明示。對於 demo，過度封鎖等於放棄學習機會；對於 live，過度放行等於把不確定性轉嫁到資金安全。

## 實作對照

| Gate / 旗標 | Demo 行為 | Live 行為 | 來源 |
|---|---|---|---|
| `cost_gate_moderate` (Rust gates.rs) | 低樣本（n<30）→ 探索模式 allow + log；統計穩健負估計才 block | N/A — live 走 `cost_gate_live` 嚴格路徑 | EDGE-DIAG-2 commit `341c093`（2026-04-28） |
| `cost_gate_live` (Rust gates.rs) | N/A | 任何負估計 / 冷啟動 / 未達門檻 → fail-closed，無 n_trades 豁免 | PH5-WIRE-1 + EDGE-DIAG-2 釘 regression test |
| `bb_breakout.active` | demo=true | live=false（G2-06 PA RFC 永久 disable 仍生效於 live） | EDGE-DIAG-2 demo-only override |
| `funding_arb.active` | demo=true | live=false（G-2 v2 verdict 仍生效於 live） | EDGE-DIAG-2 demo-only override |
| `missing_edge_fallback_bps` | -10（保守） | -10（保守） | **不動** — operator 決定不放寬 demo，因為動了會連 live 一起放寬 |
| `cost_gate_min_n_trades_for_block` | 30（demo TOML 顯式寫） | N/A — live 不讀此 knob | EDGE-DIAG-2 |
| `JS estimator min_observation_ts` | `2026-04-22T21:00Z`（post P0-13/V2-SWAP） | 同上（同份 estimates 檔，但 live 路徑用法不同） | EDGE-DIAG-2 |

## 決策啟發式（給未來 CC 接手用）

收到「應該封鎖 X 嗎 / 該允許 Y 嗎」類問題時，先按環境分支：

- **動 Live 行為（cost_gate_live、Live TOML、authorization、live_reserved）→ 預設拒絕**，要求對應 RFC + 新證據。除非 operator 明確 override，否則 live 永遠走最嚴格路徑。
- **動 Demo 行為（cost_gate_moderate、Demo TOML、demo paper-equivalent paths）→ 評估「會不會影響 live」**：
  - 如果改動只動 demo-only 路徑（`cost_gate_moderate` / `strategy_params_demo.toml` / demo-only 環境變數）→ 預設可以放寬，只要：(i) 不破 §四 五門控 (ii) 有 unit test 釘 live 不受影響
  - 如果改動會「連帶」影響 live（共用 fallback、共用 schema、共用 binary 預設值）→ 拒絕放寬，除非 operator 明確說「動」
  - 共用 binary 是常態 — 但兩條路徑在代碼層分開（`cost_gate_moderate` vs `cost_gate_live`，不同 fn）。新增 demo 放寬時必須驗 live fn 完全沒被觸碰

## 反模式（不要做）

- ❌ 用「demo 跑得也是 demo Bybit endpoint，所以放寬 live 也安全」當理由 — Live + LiveDemo + Mainnet 共用 `cost_gate_live`，LiveDemo 不因 endpoint 降級（per `feedback_live_no_degradation_by_endpoint`）
- ❌ 用「reduce code duplication」為理由把 demo + live cost_gate 合併成一個 fn — 兩條路徑刻意分開，是為了「放寬 demo 不會誤傷 live」這個不變量
- ❌ 把「demo 放寬」誤讀為「demo 沒有風控」— demo 仍走 P0/P1/P2 + 5 門控 + duplicate_position + global_notional_cap 等所有 gate，只是 cost_gate 對「估計噪音」的容忍度提高
- ❌ 看到 demo blocking 比例高就直接放寬 fallback / threshold — 先問「資料品質如何」+「多少是真信號 vs 噪音」（EDGE-DIAG-2 教訓）

## 觸發條件（什麼時候複習這個 memory）

- 任何涉及 `cost_gate*` / `risk_config*.toml` 的改動
- 任何涉及 `strategy_params_{demo,live,paper}.toml` 的 active flag 翻轉
- 看到「demo intent 通過率太低 / 太高」的 audit 觀察時
- ML / agent 上線前的「資料夠不夠」評估
- 新策略提案 / 結構性 disable 提案的 demo / live 範圍判定
