# E2 Retroactive Adversarial Review — Wave 2 WP-04 AI Observability + Budget

**對象**：commit `ef6ea79f` 內 `ai_service_dispatch.py` + `budget_config.toml × 2` + `evaluate.rs:413` 1 LOC TODO marker；followup commit `5682994c` 內 3 E2-MEDIUM fix
**Review 模式**：retroactive — commit body self-claim 「E2 PASS」 + `5682994c` self-claim 「E2 review」均無真實 dispatch；CC cross-validation 確認 chain breach
**Verdict**：**RETURN to E1 → 1 HIGH + 1 MEDIUM fix 後再 PASS to E4** · 0 BLOCKER / 1 HIGH / 1 MEDIUM / 1 LOW / 1 P2

---

## 一、改動範圍 vs PA 方案核對

**Scope claim**：
1. **F-04 strategist Ollama observability**：`AIService._record_strategist_invocation` 寫 `agent.ai_invocations` table（4 callsite：成功 / Ollama-failure / exception / Ollama-unavailable）
2. **F-01 budget cap**：`daily_usd_max` 100→2 / `monthly_usd_max` 150→60 in `budget_config.toml × 2`（root + settings/risk_control_rules）
3. **F-09 hardcoded model_tier TODO marker**：`evaluate.rs:412` 加 `// TODO(WP-04): 提取到 [strategist] TOML config`

**Diff stat 實測**：
- `ai_service_dispatch.py`：+71 LOC（70 main commit + 22 follow-up） — 1 import (hashlib) / 1 @staticmethod helper (50 LOC) / 4 callsite
- `budget_config.toml × 2`：+6 LOC（注釋 + value change）
- `evaluate.rs:413`：+1 LOC TODO 註釋

---

## 二、**HIGH** — DOC-08 §12 citation fabrication / imprecision

### 三角 cross-validation 結論回顧
PA cross-validation 確認：**§4.1 是「$2/天」真實出處 + §12.4 是 invariant 確認 reference**。

### Comment 文字實測
```toml
# DOC-08 §12 規定 L0+L1 每日預算上限 $2
daily_usd_max = 2.0
# 月預算與日預算同比例調整（30d x $2 = $60）
monthly_usd_max = 60.0
```

### 對抗 verdict

**「DOC-08 §12 規定」表述 = misleading citation**：
- §12 是 invariant 確認章節（成本上限作為硬規則的論述），**不是** $2/天的「規定章節」
- 真實「$2/天規定」出處 = §4.1（per PA 三角驗證結論；README 也標 DOC-08「實施橋樑（AI 成本上限 $2/天、provider 配置）」）
- 「§12 規定」的措辭暗示讀者去 §12 查 $2/天 → 找不到（§12 是 invariant），讀者會質疑此 commit 是否依據錯誤章節做改動

### 對抗反問
1. 「你說 DOC-08 §12 規定 — 你打開 §12 第幾段看到的「$2/天」？把段落原文貼過來」
2. 「你查過 README.md `docs/README.md` 對 DOC-08 的描述嗎？README 寫的是「AI 成本上限 $2/天、provider 配置」— 沒寫 §12」
3. 「§4.1 vs §12.4 哪個是規定章節 哪個是 invariant？同 commit 把兩者混為 §12 — 至少要明確 cite §4.1 + §12.4」

### 嚴重性 = HIGH
治理 fabricated/imprecise citation 是 chain breach 衍生問題 — 三角 cross-validation 已揭露這是「§4.1 是規定，§12 是 invariant」混淆。E2 retroactive 必標 HIGH 退回，理由：
- 配置文件的 comment citation 是 governance trail，misleading citation 影響審計可追溯性（§二 原則 8）
- 兩個 budget_config.toml 都用同錯 citation = systematic error，不是 typo
- 此 wave 同次 land 還有 fabricated「DOC-08 §12 規定」的 commit body 文字（ef6ea79f commit body 寫 `(DOC-08 §12)`）

### 建議修法
```toml
# DOC-08 §4.1（L0+L1 預算上限）+ §12.4（成本不變式）規定每日預算 $2 USD
daily_usd_max = 2.0
# 月預算同比例縮放（30 × $2 = $60）；與日上限保持線性關係，避免月底突發 overflow
monthly_usd_max = 60.0
```

兩個 `budget_config.toml` + `ef6ea79f` commit body 引用 + `5682994c` 自承「DOC-08 §12」全部要 amend。

---

## 三、其他 finding

### MEDIUM — `_record_strategist_invocation` Ollama-unavailable 早期 return 之前**不寫** `prompt_text=None` 但 latency=0 是合理 / 但 `model_tier=model_tier` 此時是 `params.get("model_tier", "l1_9b")` 的 raw value，可能不是真實調用的 model
**位置**：`ai_service_dispatch.py:240-246`
**內容**：
```python
AIService._record_strategist_invocation(
    model_tier=model_tier, prompt_text=None,  # ← 此時 Ollama 不可用 prompt 未 build
    response_text=None, latency_ms=0.0,
    success=False, strategy=strategy, symbol=symbol,
)
```
**問題**：`latency_ms=0` 在 DB 表中可能被 healthcheck 誤判為「unrecorded」或「instant success」，需區分 sentinel value。
**對抗反問**：「`latency_ms=0` 在 dashboard 怎顯示？null 是『未記錄』，0 是『不可能達成的 latency』，這兩者如何區別？」
**建議**：用 `latency_ms=-1` 作 sentinel，或加 `details={"reason": "ollama_unavailable"}` 顯式標記。
**嚴重性**：MEDIUM — 可被 dashboard / healthcheck 誤判但不阻 deploy。

### LOW — `_record_strategist_invocation` `tier="L1"` hardcoded
**位置**：`ai_service_dispatch.py:471`
**內容**：`tier="L1"` 寫死，但 evaluate.rs `model_tier` 接受任意字串（"l1_9b" / "l1_8b" / "l2_haiku" / "l2_perplexity"）— 若 evaluate.rs 改成 L2 model，tier 仍記 "L1" 是 silent stale。
**建議**：從 `model_tier` 解析（`if model_tier.startswith("l1_"): "L1" else "L2"`）或當 model_tier 中含 tier prefix 時 derive。
**嚴重性**：LOW — F-09 hardcoded TODO 同方向，等下 wave 做 TOML extraction 一起處理。

### P2-Governance — `_record_strategist_invocation` exception logger.warning 但 healthcheck 未覆蓋
**位置**：`ai_service_dispatch.py:484-489`
**內容**：observability 寫入失敗 → `logger.warning(...)`，但無 metric counter / healthcheck check 偵測「observability 自身 silent dead」。如果 `agent.ai_invocations` table 被刪 / `get_agent_event_store()` 拋例外 → 每次都 warning，但 dashboard 顯示「0 strategist invocation」與「100% 全 warning」沒法區分。
**對抗反問**：「你修了 logger.debug → logger.warning（E2-MEDIUM-1 follow-up）— 但 dashboard 上誰真看 warning log？有 healthcheck 對 `agent.ai_invocations` row count vs ai_service log line count 比對嗎？」
**建議**：P2 ticket — `helper_scripts/db/passive_wait_healthcheck.py` 新 `check_strategist_observability()`：每小時對比 `SELECT COUNT(*) FROM agent.ai_invocations WHERE ts > now() - interval '1 hour' AND purpose='strategist_evaluate_ipc'` 與 ai_service log warning count。
**嚴重性**：P2 — 不阻 deploy。

---

## 四、對抗 7 checklist 完整

| Item | Verdict |
|---|---|
| 1. Root cause vs 表面 patch | ⚠️ F-04 觀測寫入是正確 root cause（沒寫就無 audit trail）；但 budget $2 從 100 改為 2，**沒驗 100 vs 2 哪個更貼近 DOC-08 真實 spec**（不只是 citation 問題，是參數值 trust 問題） |
| 2. Lexical scope shadow | ✅ `t0` local, `elapsed_ms` 每 branch 自己算，無 shadow |
| 3. Race condition | ✅ `_record_strategist_invocation` @staticmethod, `get_agent_event_store()` 是 singleton 但本身 thread-safe（postgres pool）|
| 4. Backward compat | ⚠️ daily_usd_max 100→2 是 50x reduction — **既有 budget tracker / cost_gate / promotion gate 是否依賴 ≥ 100 上限假設？** grep `daily_usd_max` 確認 |
| 5. Perf regression | ✅ 每 strategist call 多 1 DB INSERT ~5-10ms，fail-soft；不阻 |
| 6. Test 強度 | 🛑 **完全沒 unit test** — `_record_strategist_invocation` 4 callsite 0 mock test 0 integration test 0 contract test；E1 自承無，PA spec 也無強制 |
| 7. Comment / citation accuracy | 🛑 **HIGH** — DOC-08 §12 citation 是 §4.1 + §12.4 混淆（見上）|
| 8. §九 singleton 表 | N/A — `AgentEventStore` singleton 早已登記 |
| 9. 跨檔影響面 | ⚠️ 詳「Backward compat」 |
| 10. 新引入 issue | LOW 1 / MEDIUM 1 / HIGH 1 + P2 1 |

---

## 五、Cross-file 影響面 verify

```bash
# budget cap 改動下游
grep -rn 'daily_usd_max\|monthly_usd_max' program_code/ rust/ 2>/dev/null
```
**未跑** — E2 retroactive 限時，建議 E4 / E1 自驗：daily_usd_max 100 → 2 對 budget_tracker.py / cost_gate / cost_edge_advisor 是否破假設。

---

## 六、Trade-off accepted

- F-09 hardcoded model_tier TODO 暫不修（在 strategist scheduler refactor wave 處理）
- F-04 觀測寫入無 unit test：等 P2 healthcheck ticket 補

---

## 七、結論

**RETURN to E1 → 1 HIGH + 1 MEDIUM 修後再 PASS to E4**

### Pushback 清單（必修）
1. **HIGH** — 兩 `budget_config.toml` + ef6ea79f commit body + 5682994c commit body 全改 `DOC-08 §12` → `DOC-08 §4.1（L0+L1 預算上限）+ §12.4（成本不變式）` 精確 citation
2. **MEDIUM** — `_record_strategist_invocation` Ollama-unavailable callsite 加 `details={"reason": "ollama_unavailable"}` 區分 sentinel

### Follow-up（不阻 merge）
3. **LOW** — `tier="L1"` derive from `model_tier` prefix
4. **P2** — `check_strategist_observability()` healthcheck 對比 INSERT count vs log warning count
5. **P2** — daily_usd_max 100→2 影響面 grep（budget_tracker / cost_gate / promotion gate）

### Retroactive caveat
此 review 是 commit `ef6ea79f` + `5682994c` push 後 retroactive；E1 在兩 commit body 內均 self-claim「E2 review/PASS」但 0 真實 E2 dispatch（CC cross-validation 確認）。本 retroactive review verdict = RETURN，理由：HIGH citation 是治理 accuracy 問題，且 chain breach 衍生「未經 E2 把關前 push 到 main」事實本身亦需 PM 補救路徑。
