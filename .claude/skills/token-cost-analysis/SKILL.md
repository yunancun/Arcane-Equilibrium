---
name: token-cost-analysis
description: Layer 2 AI 推理（Ollama L1 / Claude L2 / LM Studio）token 用量、成本歸因、cost_edge_ratio 監控；AI-E agent 純分析。
allowed-tools: Read, Grep, Glob, Bash
---

# Token / Cost Analysis（AI 成本分析）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S3 上層 drift 防線**：本 skill 引用上層（CLAUDE.md / DOC-XX / SM-XX / EX-XX）為 extract；原文修改後可能漂移，發現不一致以原文為準。

> ⚠️ **Cost limit / SLA 數字 disclaimer**：「每日 $2 硬上限」「L1 < 3s」「cost_edge_ratio ≥ 0.8」等具體數字以 **DOC-08 V1 + CLAUDE.md §二 原則 13** 原文為準；本 skill 為 extract，數字若有出入 → 以治理為準。

## 何時觸發

- AI-E 收到「token 成本審計」「cost_edge_ratio 評估」「Layer 2 預算超標」
- 月度 AI 成本回顧
- 新 Layer 2 工具 / agent 上線前 cost projection
- CLAUDE.md §二 原則 13（AI 成本感知）相關決策

## OpenClaw AI 三層成本結構

| 層 | Provider | 成本 | 觸發 |
|---|---|---|---|
| L0 確定性 | 本地規則 | 0 | 永遠 |
| L1 本地 LLM | Ollama / LM Studio（Mac dev） | 0 邊際（電費忽略） | thought_gate 通過 |
| L2 雲端 | Claude API（Anthropic） | $$$ per 1M tokens | budget gate + model_router |

CLAUDE.md §二 原則 14：**L0+L1 必須夠跑基礎運營**，L2 為加值不為必需。

## 觀察點（log / DB / API）

### Ollama / LM Studio（本地，無賬單但要監 latency + 失敗率）
```bash
# Ollama 內建 log
journalctl -u ollama -f --since "1 hour ago"

# LM Studio：應用內 log + 模型載入時間
# Mac：~/Library/Application Support/LM Studio/logs/
```

### Claude API 用量
- Anthropic console（https://console.anthropic.com/settings/usage）
- per-request `usage.input_tokens` + `usage.output_tokens` + `usage.cache_*` log 入 DB
- OpenClaw 自記：`learning.layer2_cost_log` table（schema 待確認）

### 內部記錄
```sql
-- 預期 schema（依 CLAUDE.md §五）
SELECT
  provider,                            -- ollama / claude / lm_studio
  model,                               -- claude-opus-4-7 / qwen3.6-35b
  request_type,                        -- agent name / tool name
  input_tokens, output_tokens,
  cache_creation_tokens, cache_read_tokens,
  cost_usd,
  ts
FROM learning.layer2_cost_log
WHERE ts > NOW() - INTERVAL '7 days'
GROUP BY provider, model, request_type
ORDER BY SUM(cost_usd) DESC LIMIT 20;
```

## 三大分析

### 1. cost_edge_ratio（CLAUDE.md §二 原則 13）

```
cost_edge_ratio = AI_cost_per_trade / expected_edge_per_trade
```

- ratio < 0.3：健康（AI 加值明顯）
- ratio 0.3 – 0.8：觀察（邊際遞減中）
- ratio ≥ 0.8：**建議關倉 / 降頻 / 換 L1-only**（原則 13 強制）
- 計算頻率：每策略 × 每天 + 全局滾動 7d

### 2. Token 浪費熱點

掃描：
- **Prompt cache miss**：cache_creation 高但 cache_read 低 → prompt 結構不穩定
- **過長 system prompt**：input_tokens P95 > 8K 但任務簡單 → 應拆 sub-agent / 縮 context
- **過短 output 但高 input**：output < 100 tokens 但 input > 5K → 應移到 L1
- **重複工具呼叫**：同 trace_id 內 same tool 呼 ≥ 3 次 → 邏輯 bug
- **streaming 但未用**：開了 stream 但 client buffering → 浪費 stream overhead

### 3. 模型路由效益

`model_router.py`（CLAUDE.md §五 H1-H5）應該按任務分流：
- 簡單分類 / yes-no → L1（Ollama / LM Studio）
- 複雜推理 / 工具調用 → Claude Sonnet / Opus
- audit：`SELECT request_type, model, AVG(cost_usd) FROM ... GROUP BY 1,2`
- 紅旗：簡單任務跑 Opus、複雜推理跑 Haiku（router 失效）

## 預算 Gate（H2 budget）

CLAUDE.md §五 H1-H5 治理層含 budget。AI-E 必驗：
- [ ] daily budget cap 設置（避免月底意外賬單）
- [ ] gate 計算 = (本日累計 + 預估本筆) ≤ cap
- [ ] 超 80% 警告 + 超 100% fail-closed
- [ ] cap 修改有 audit log

## OpenClaw 特定關注

- **Layer 2 自主推理循環（gap，TODO §G-1）**：上線前必先 cost projection
- **Mac dev 用 LM Studio + Qwen3.6-35B**：本地審核成本 = 0，但要監 GPU/CPU 占用 vs 寫碼任務的 trade-off
- **memory 增長**：context cache 留 5min，session 多時 cumulative input tokens 暴增 → cache_read_tokens 比例應 ≥ 50%
- **Operator 月度賬單**：總成本 ÷ 月內 commit 數 = AI 對開發效率的單位成本

## 工作流（5 步）

1. **拉資料** — 7d / 30d Anthropic console + DB cost_log + Ollama log
2. **分組** — by provider / by model / by request_type / by trace_id
3. **計 cost_edge_ratio** — 每策略每天 + 全局滾動
4. **找熱點** — 套上述 5 種浪費 pattern 掃
5. **產出** — `docs/CCAgentWorkSpace/AI-E/workspace/reports/YYYY-MM-DD--cost_audit.md`

## 輸出格式

```markdown
# AI-E 成本審計 — <period> · <date>

範圍：<7d / 30d>
總成本：$X.XX
分佈：Claude $X / Ollama $0 / LM Studio $0

## cost_edge_ratio 分布
| 策略 | ratio | 結論 |
|---|---|---|
| bb_breakout | 0.42 | 健康 |
| funding_arb | 1.21 | **建議關倉**（原則 13） |

## Token 浪費熱點
| 模式 | 範圍 | 估計浪費 | 建議 |
|---|---|---|---|

## 模型路由
| request_type | 主用 model | 月成本 | 建議 |
|---|---|---|---|

## 預算 Gate 健康
- daily cap：$X
- 本期超限次數：N

## 下輪建議
- ...
```
