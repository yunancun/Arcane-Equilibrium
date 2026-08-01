---
name: token-cost-analysis
description: AI-E agent 純分析：AI token 成本審計、cost_edge_ratio 評估、Layer 2 預算超標、月度成本回顧、新 L2 工具上線前 cost projection 時讀。
allowed-tools: Read, Grep, Glob, Bash
---

# Token / Cost Analysis（AI 成本分析）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：LLM 計價 / cache / batch 機制通識不在本檔重述；本檔只列本專案的成本結構、判準與 SSOT 指針。**模型名與單價即時查證官方 pricing 頁 / console，不信本檔示例與記憶。**

> **S3 上層 drift 防線**：本 skill 引用上層（CLAUDE.md / DOC-XX / SM-XX / EX-XX）為 extract；原文修改後可能漂移，發現不一致以原文為準。
> ⚠️ **Cost limit / SLA 數字 disclaimer**：「每日 $2 硬上限」「L1 < 3s」「cost_edge_ratio ≥ 0.8」等具體數字以 **DOC-08 V1 + `CLAUDE.md` Root Principles** 原文為準；本 skill 為 extract，數字若有出入 → 以治理為準。

## 何時觸發

- AI-E 收到「token 成本審計」「cost_edge_ratio 評估」「Layer 2 預算超標」
- 月度 AI 成本回顧；新 Layer 2 工具 / agent 上線前 cost projection
- development sub-agent workflow / agent-wave / Full Audit 的 token、cache、tool、retry、fan-out、rework ROI

## OpenClaw AI 三層成本結構

| 層 | Provider | 成本 | 觸發 |
|---|---|---|---|
| L0 確定性 | 本地規則 | 0 | 永遠 |
| L1 本地 LLM | Ollama / LM Studio（Mac dev） | 0 邊際 | thought_gate 通過 |
| L2 雲端 | Claude API（Anthropic） | $$$ per 1M tokens | budget gate + model_router |

`CLAUDE.md` Root Principles：**L0+L1 必須夠跑基礎運營**，L2 為加值不為必需。

## 觀察點

- 本地（Ollama / LM Studio）：無賬單但監 latency + 失敗率（journalctl / 應用內 log）
- Claude API：Anthropic console usage 頁 + per-request `usage.*` log 入 DB
- 內部記錄：`learning.layer2_cost_log` table（schema 待確認；欄位含 provider / model / request_type / input·output·cache tokens / cost_usd / ts），按 provider / model / request_type 分組取 7d/30d

## 核心分析

### 1. cost_edge_ratio（Root Principles）

`cost_edge_ratio = AI_cost_per_trade / expected_edge_per_trade`
- < 0.3 健康；0.3–0.8 觀察（邊際遞減中）；**≥ 0.8 建議關倉 / 降頻 / 換 L1-only**（原則 13 強制）
- 計算頻率：每策略 × 每天 + 全局滾動 7d

### 2. Token / orchestration 浪費熱點（掃描清單）

- **Prompt cache miss**：cache_creation 高但 cache_read 低 → prompt 結構不穩定
- **context 與 complexity 不匹配**：mandatory evidence 很少但 input P95 遠高於同類 durable closure；先查 universal preload/重複 source，再決定拆分。複雜/Full Audit 不以 8K 類固定 cap 裁切
- **過短 output 但高 input**：output < 100 tokens 但 input > 5K → 應移到 L1
- **重複工具呼叫**：同 trace_id 內 same tool 呼 ≥ 3 次 → 邏輯 bug
- **fan-out 低產出**：spawn 增加但 accepted decision-changing findings / verdict reversals / avoided rework 不增
- **retry 無新資訊**：同 input/model/task shape 裸重試；合法 retry 必有 infrastructure-null、context/model/shape 改變或 checkpoint resume
- **報告年金**：per-role report/memory 被後續重讀但沒有新 durable lesson
- **false economy**：token 下降但 NEEDS_CONTEXT、reopen、operator reversal 或 false closure 上升

### 3. 模型路由效益

`model_router.py`（H1-H5 governance path）按任務分流：簡單分類 / yes-no → L1；複雜推理 / 工具調用 → L2（現役型號以 runtime config + 官方 pricing 為準）。紅旗：簡單任務跑高價 L2 型號、複雜推理跑最低階型號（router 失效）。

### 4. Cache / Batch 審計軸

TTL 選型是否匹配呼叫頻率；命中率 = `cache_read_tokens / total_input_tokens` 追蹤；非延遲敏感離線分析（週報 / 月度回顧 / 批量歸因）是否已走 Batch API（折扣以官方 pricing 為準）。

## 預算 Gate（H2 budget）

- [ ] daily budget cap 設置；gate 計算 = (本日累計 + 預估本筆) ≤ cap
- [ ] 超 80% 警告 + 超 100% fail-closed；cap 修改有 audit log

## Development-agent consumption scorecard

主指標：`total model/tool/time cost / durable accepted closure`。同時列：input/output/cache tokens（無 telemetry 標 unavailable）、agent/tool calls、fan-out、retry、wall time、accepted decision-changing findings、verdict reversal、rework/reopen、false-positive、operator reversal、context envelope target/reserve 使用原因。

Cache hit、tokens/call、findings count、roles skipped、DONE 數都只是診斷量，不能單獨最佳化。Prompt cache TTL/定價/折扣以當前官方文件與 console 為準；不要在 skill 寫死命中率或成本門檻。

## 工作流（5 步）

1. **拉資料** — 7d / 30d Anthropic console + DB cost_log + 本地 log
2. **分組** — by provider / model / request_type / trace_id
3. **計 cost_edge_ratio** — 每策略每天 + 全局滾動
4. **找熱點** — 套 §2 浪費 pattern 掃
5. **產出** — 回 immutable `role_fragment_v1` with `payload_kind=finding_fragment_v1`；不自動寫 role report/memory

## 輸出格式

```markdown
# AI-E 成本審計 — <period> · <date>

範圍：<7d / 30d>
總成本：$X.XX（分佈：Claude / Ollama / LM Studio）

## cost_edge_ratio 分布
（數值必從本次拉數計算，勿照抄示例）
| 策略 | ratio | 結論 |
|---|---|---|

## Token 浪費熱點
| 模式 | 範圍 | 估計浪費 | 建議 |
|---|---|---|---|

## 模型路由
| request_type | 主用 model | 月成本 | 建議 |
|---|---|---|---|

## 預算 Gate 健康
daily cap / 本期超限次數

## 下輪建議
- ...
```
