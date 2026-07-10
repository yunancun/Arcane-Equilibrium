# E1 報告 — R3 修復包 WP-C#1：ai_pricing.yaml 補 claude-sonnet-5 定價鍵

日期：2026-07-10
Charter：r3_fix_charter.md WP-C 第 1 點（scratchpad）
範圍鎖定：只動 `settings/ai_pricing.yaml`（另按完成序列追加 E1 memory.md 一節）

## 任務摘要

為 L2 解凍一鍵（WP-C）補 `claude-sonnet-5` 定價鍵，使 budget gate / cost tracker
（`rust/openclaw_engine/src/ai_budget/pricing.rs`）對該 model 名不再 fail-closed 拒記帳。

## 權威定價查證

- claude-api skill 本地不存在（查過 `/Users/ncyu/Projects/TradeBot/.claude/skills/`、
  `srv/.claude/skills/`、`~/.claude/skills/`、plugins marketplace），按 charter fallback 官方文檔。
- 官方來源：`platform.claude.com/docs/en/docs/about-claude/pricing`（2026-07-10 查核）：
  - intro 價 **$2 / $10 per MTok**（input/output），窗口 **至 2026-08-31 止**；
  - 2026-09-01 起標準價 $3 / $15；
  - API model ID 即 `claude-sonnet-5`（官方 news 頁確認裸名）；
  - sonnet-5 用新 tokenizer，同文本 tokens 約 +30%（記帳以 API 回報 usage 為準，僅注釋提示）。

## 修改清單

| 檔 | 改動 |
|---|---|
| `settings/ai_pricing.yaml` | header `Last updated` 2026-06-14→2026-07-10 + 一行變更紀錄；anthropic 段 opus-4-8 與 sonnet-4-6 之間插入 `claude-sonnet-5`（input_per_mtok 2.00 / output_per_mtok 10.00 / active: true）+ 4 行中文注釋（intro 窗口至 2026-08-31、TODO 2026-09-01 到期改 3.00/15.00、tokenizer 提示） |

## 關鍵 diff（新增條目）

```yaml
  # claude-sonnet-5 intro 定價（2026-07-10 查核 platform.claude.com/docs pricing 官方頁）：
  # $2/$10 per MTok 為 intro 窗口價，至 2026-08-31 止；2026-09-01 起官方標準價 $3/$15。
  # TODO(2026-09-01 到期)：intro 窗口結束後須改 input 3.00 / output 15.00，否則低估成本。
  # 注意：sonnet-5 用新 tokenizer，同文本 tokens 約 +30%；記帳以 API 回報 usage 為準。
  claude-sonnet-5:
    input_per_mtok: 2.00
    output_per_mtok: 10.00
    active: true
```

## 自測證據（可重跑）

`python3 -c` 模擬 pricing.rs 載入語義（兩層 flatten、有限/非負費率、active bool）：

- parse OK；total 11 / active 9（boot sanity `active_count()>=5` 持續滿足）；
- `claude-sonnet-5` = {2.0, 10.0, active:true}；sample cost 1000in/500out = $0.007；
- pricing.rs Test 8 spot-check 不受影響（`claude-sonnet-4-6` active、`claude-sonnet-4-5` inactive 均未動）；
- Python 側（provider_pricing_catalog / test_layer2）走 tier 別名→真名正規化，無精確計數斷言，加 key 零破壞。

## 治理對照

- 定價值取 intro 現價（記帳準確，E2E-1 one-shot 成本證據與實際帳單一致），非保守高估——
  理由：現價無不確定性，窗口到期風險以注釋 TODO(2026-09-01) 顯式落地。此為 E1 小決策，E2 可覆議。
- 未動任何硬邊界字段；未新增 migration / singleton / script；只中文新注釋。
- 未 commit / 未 push（charter 指令，由後續統一步驟做）。

## 不確定之處

- yaml 無 schedule 機制，2026-09-01 換標準價依賴人工 TODO——建議 PM 在 TODO.md 收尾時加一條
  帶日期的 follow-up（本 E1 不越界改 TODO.md，WP-C 收尾歸 PM）。
- cargo 在 Mac 不可用，pricing.rs 真實測試留 E4 Linux 回歸（`cargo test -p openclaw_engine ai_budget`）。

## Operator / PM 下一步

1. E2 對抗審查本 diff；2. E4 Linux 回歸含 pricing.rs Test 8；3. TODO.md 記 2026-09-01 定價更新 follow-up。

E1 IMPLEMENTATION DONE: 待 E2 審查
