# CLAUDE.md §五 架構總覽 — Pre Alpha Surface framing 快照

**Archive 觸發**：W-AUDIT-8a "Alpha Surface Foundation" spec phase 落地（2026-05-09）
**原因**：PA audit `2026-05-09--full_loss_architectural_root_cause_redesign.md` Layer 3.1 指出舊 framing 「KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator」在文檔層面強化「TA-only 路徑為預設」的 mental model，使任何系統孵化的策略都會 regress 到 textbook TA。為配合 R-1 接口升級，§五 改為含 AlphaSurface 一等對象的 framing。
**Spec**：`docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`

---

## 舊 §五 全文（archived，截至 2026-05-09 W-AUDIT-1 sync）

```
[數據與觀察層]           Bybit REST + WS → Postgres + Observer
[H0 本地判斷內核]        freshness / health / eligibility / risk envelope（<1ms SLA）
[GovernanceHub]          SM-01 授權 + SM-04 風控 + SM-02 租約 + EX-04 對賬
[H1-H5 AI 治理層]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       (*) GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 209 /api/v1 + non-api GUI 路由 + `/api/v1/openclaw/*` planned aggregation
[GUI + Learning]         OpenClaw Control Console（唯一 GUI；13 tabs）+ Learning Cockpit + Paper Trading Dashboard
[OpenClaw Gateway]       外圍通信 / mobile / supervisor / proposal relay；非交易 hot path，非第二 GUI
[Rust openclaw_engine]   paper / demo / live 三模式唯一引擎（1C-3-F 後）
                         tick pipeline + IntentProcessor + paper_state + governance + stop_manager
[Compute tiers]          L0 確定性 → L1 Ollama → L1.5 (Haiku/Perplexity) → L2 Claude manual/supervisor escalation only
[風控框架]               P0/P1/P2 三層 + 對抗性止損 + AI 注意力稅
[策略工具包]             KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator
[管線橋接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate
[止損管理器]             StopManager: Hard/Trailing/Time Stop + ATR 動態倉位
```

---

## 新 §五 [策略工具包] 行 reframe

**舊**：`[策略工具包]    KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator`

**新**：`[策略工具包]    KlineManager → IndicatorEngine → AlphaSurface (TA + Funding/OI/Orderflow/Event/Regime) → SignalEngine → 5 策略 → Orchestrator`

舊 framing 保留至此 archive 供 reference。

---

## 變更紀錄

- 2026-05-09：W-AUDIT-8a spec phase 落地，§五 reframe 完成，舊 framing 歸檔此處。
