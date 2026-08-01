---
name: feedback_model_effort_tiering
description: operator 2026-08-01 裁決:22 角色模型/effort 三級分級;thinking 治理改 per-lane effort;subagent 委派需上限非鼓勵
metadata:
  node_type: memory
  type: feedback
---

# 模型/effort 三級分級(operator 2026-08-01 裁決)

2026-08-01 框架健檢(23/23 findings CONFIRMED)揭示:22 角色全部 `model: inherit`、renderer 側 22/22 `effort=high` 硬編碼、registry 資料模型無法表達模型分層;sonnet+haiku 月使用率僅 0.5%,fable-5(2× Opus 單價)被用於日常開發。operator 裁決三級分級:

- **T1 opus/high**(判斷密集,錯誤代價高):PM、E1、E1a、E2、E3、CC、QC、MIT、PA
- **T2 opus/low**(程序性審查/運維):E4、FA、OPS、E5、QA、AI-E、BB、IB
- **T3 sonnet/medium**(格式/文檔/巡檢):TW、R4、A3

配套治理轉向:

1. **thinking 治理改 per-lane effort**:舊鐵則「關閉 Adaptive Thinking」已退役——Fable 5 thinking 不可關(API 回 400),Opus 5 僅 effort≤high 可關,且 thinking 只佔總成本 ~1%,不是槓桿。控制成本的正確旋鈕是 per-lane effort 分級,不是關 thinking。
2. **subagent 委派需上限而非鼓勵**:舊鐵則「強制先評估 sub-agent 拆分」已退役——Opus 5 官方 migration 指引明言新世代模型已過度委派,舊的「多委派」引導應刪除並加上限。委派決策以「一個 subagent 是否帶來淨決策增益」為準,不是默認拆分;月 output 65% 在 subagent 是本裁決的量化背景。
3. 落地面:registry schema 加 model/effort 欄+renderer 透傳,見 `agent/fw-model-tiering-20260801` lane;本檔為政策正本,分級調整需 operator 裁決。

兩條被退役鐵則原檔(含 superseded 註記)在 `archive/feedback_subagent_first.md` 與 `archive/feedback_disable_adaptive_thinking.md`;健檢弧見 [[project_2026_08_01_framework_health_audit]]。
