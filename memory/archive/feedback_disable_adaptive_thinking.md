---
name: 關閉 Adaptive Thinking（延伸思考）
description: Claude 回應時不使用 adaptive thinking / extended thinking 模式，直接輸出答案。
type: feedback
originSessionId: 189878ce-df95-4b97-a566-ea1b4e395fe9
---

> **SUPERSEDED 2026-08-01(框架健檢裁決)**:Fable 5 thinking 不可關(API 回 400)、Opus 5 僅 effort≤high 可關,且 thinking 僅佔總成本 ~1% 非槓桿;政策由 [[feedback_model_effort_tiering]] 承接(per-lane effort 分級)。留檔為史。
不使用 adaptive thinking（Claude 的延伸思考 / extended thinking 功能）。

**Why:** 增加延遲與成本，對本項目工程任務沒有對應的品質提升。Operator 明確要求關閉。

**How to apply:** 所有回應直接輸出，不啟用思考模式。收到工程任務時，直接分析並行動，不進入延伸推理塊。
