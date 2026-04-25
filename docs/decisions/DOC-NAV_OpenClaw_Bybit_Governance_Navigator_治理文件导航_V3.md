**DOC-NAV**

Governance Document Navigator

治理文件導航

OpenClaw / Bybit AI Agent Trading System

**Version 3.0  —  2026-03-29**

*20 Formal Documents  \|  Classification: Internal*


# 修訂歷史 / Revision History

| **Date** | **Ver** | **Author** | **Changes** |
|---|---|---|---|
| 2026-03-24 | 1.0 | Claude / Operator | Initial navigator (12 documents) |
| 2026-03-26 | 2.0 | Claude / Operator | Expanded to 18 documents + V1.1 updates |
| 2026-03-26 | 2.1 | Claude / Operator | Minor corrections |
| 2026-03-29 | 3.0 | Claude / Operator | V2 expansion: 20 formal documents. Updated 6 docs to V2 (DOC-01/02/04/06, EX-01/05). Added 2 new docs (EX-06/07). Updated reading order and change routing. |


# §1 文件註冊表 / Complete Document Registry

The governance document set consists of 20 formal documents organized into four categories.


## §1.1 DOC 系列 — 核心治理 / Core Governance (8 documents)

| **ID** | **中文** | **Version** | **Date** | **Description** |
|---|---|---|---|---|
| **DOC-NAV** | 導航 | V3.0 | 2026-03-29 | This document. Entry point and index for all governance documents. |
| **DOC-01** | 憲法 | V2.0 | 2026-03-29 | Root principles. 16 constitutional articles including Multi-Agent, adversarial awareness, AI attention tax. |
| **DOC-02** | 邊界定義 | V2.0 | 2026-03-29 | Where Agent can act. H0–H5 as Multi-Agent precursors, AI tool boundaries, execution matrix. |
| **DOC-03** | 字段規範 | V1.1 | 2026-03-26 | Field specification for all data structures. No V2 needed. |
| **DOC-04** | 能力藍圖 | V2.0 | 2026-03-29 | What Agent can do. A–J ten capabilities, 6 product families, strategy autonomy, Analyst L1–L5. |
| **DOC-05** | Truth Source | V1.1 | 2026-03-26 | Source of truth definitions. No V2 needed. |
| **DOC-06** | 變更治理 | V2.0 | 2026-03-29 | How changes are governed. Three-color classification (GREEN/YELLOW/RED), empowerment flow. |
| **DOC-07** | 事故治理 | V1.1 | 2026-03-26 | Incident response procedures. No V2 needed. |
| **DOC-08** | 實施橋樑 | V1.0 | 2026-03-29 | Technical implementation. L0–L2 compute paths, Ollama deployment, AI budget, Bybit V5 mapping. |


## §1.2 EX 系列 — 執行邊界 / Execution Boundaries (7 documents)

| **ID** | **中文** | **Version** | **Date** | **Description** |
|---|---|---|---|---|
| **EX-01** | 風控邊界 | V2.0 | 2026-03-29 | P0/P1/P2 three-tier risk, Guardian adaptive, adversarial stops, attention tax, portfolio risk. |
| **EX-02** | OMS 邊界 | V1.1 | 2026-03-26 | Order Management System boundaries. No V2 needed. |
| **EX-03** | Control Plane | V1.1 | 2026-03-26 | Control plane boundaries. No V2 needed. |
| **EX-04** | Reconciliation | V1.1 | 2026-03-26 | Reconciliation boundaries. No V2 needed. |
| **EX-05** | 學習邊界 | V2.0 | 2026-03-29 | Evolution Engine L1–L5, strategy incubation, transfer learning, regime prediction. |
| **EX-06** | Multi-Agent | V1.0 | 2026-03-29 | 5 Agent roles (Scout/Strategist/Guardian/Analyst/Executor), orchestration, conflict arbitration. |
| **EX-07** | 感知平面 | V1.0 | 2026-03-29 | 10 data sources, freshness model, event calendar, Agent data access matrix. |


## §1.3 SM 系列 — 狀態機 / State Machines (4 documents)

| **ID** | **中文** | **Version** | **Date** | **Description** |
|---|---|---|---|---|
| **SM-01** | 授權 SM | V1.1 | 2026-03-26 | Authorization state machine. No V2 needed. |
| **SM-02** | Decision Lease SM | V1.1 | 2026-03-26 | Decision Lease lifecycle state machine. No V2 needed. |
| **SM-03** | OMS SM | V1.1 | 2026-03-26 | Order Management state machine. No V2 needed. |
| **SM-04** | 運行模式 SM | V1.1 | 2026-03-26 | System run mode state machine. No V2 needed. |


## §1.4 歷史文件 / Historical Documents (2 documents, archived)

| **ID** | **中文** | **Version** | **Date** | **Description** |
|---|---|---|---|---|
| **HIST-01** | 歷史過渡 | V1.0 | 2026-03-24 | Historical transition notes from early development. Archived, not maintained. |
| **HIST-02** | 歷史編號 | V1.0 | 2026-03-24 | Old numbering system mapping (D21/D22/G1-G6 etc.). Archived, not maintained. |


# §2 建議閱讀順序 / Recommended Reading Order

Different audiences should read documents in different orders.


## §2.1 全面理解（新人）/ Complete Understanding (New Reader)
- **DOC-NAV V3** — This navigator (you are here)
- **DOC-01 V2** — Constitution: understand the root principles first
- **DOC-04 V2** — Capability Blueprint: what the system can do (A–J)
- **DOC-02 V2** — Boundary Definition: where the Agent operates
- **EX-01 V2** — Risk Control: how safety is enforced
- **EX-06 V1** — Multi-Agent: who does what
- **EX-05 V2** — Learning: how the system evolves
- **DOC-06 V2** — Change Governance: how changes are controlled
- **DOC-08 V1** — Implementation Bridge: technical details
- **EX-07 V1** — Data Plane: data sources and freshness
- **Remaining docs** — as needed for specific topics


## §2.2 風控專題 / Risk Control Focus
- **DOC-01 V2** → **EX-01 V2** → **DOC-02 V2 §5** → **EX-06 V1** (Guardian role) → SM-01/02


## §2.3 學習與進化專題 / Learning & Evolution Focus
- **DOC-01 V2** → **EX-05 V2** → **DOC-04 V2 §6** (Analyst L1–L5) → **DOC-06 V2** → **EX-07 V1**


## §2.4 技術實現專題 / Technical Implementation Focus
- **DOC-08 V1** → **DOC-04 V2 §3** (product families) → **EX-07 V1** → **DOC-03 V1.1** → SM-01/02/03/04


# §3 V2 擴展摘要 / V2 Expansion Summary

The V2 expansion was conducted on 2026-03-29 to align governance documents with the system’s evolved Multi-Agent architecture, full-category trading design, and learning engine capabilities.


## §3.1 變更統計 / Change Statistics
- **Documents updated to V2: **6 (DOC-01, DOC-02, DOC-04, DOC-06, EX-01, EX-05)
- **Documents created as V1: **2 (EX-06 Multi-Agent, EX-07 Data Plane)
- **Documents added in prior V2 session: **1 (DOC-08 Implementation Bridge V1)
- **Documents unchanged: **10 (DOC-03/05/07, EX-02/03/04, SM-01/02/03/04)
- **Historical archived: **2 (HIST-01, HIST-02)
- **Total formal documents: **20


## §3.2 主要新增內容 / Key New Content
- **Multi-Agent architecture: **OpenClaw as Conductor + 5 Agents (Scout/Strategist/Guardian/Analyst/Executor)
- **A–J capability goals: **10 capability targets with completion tracking and gate phases
- **P0/P1/P2 three-tier risk: **merge formula effective = min(P0??P1, P1) with complete parameter list
- **Adversarial stop design: **dual-layer stops + concealment + 6 anti-hunt mechanisms
- **AI attention tax: **cost_edge_ratio grading A–F with auto-close and protection mechanisms
- **Analyst evolution L1–L5: **from post-trade review to meta-learning with unlock criteria
- **Strategy incubation: **autonomous paper deployment → auto-promotion when gate criteria met
- **Three-color change governance: **GREEN (auto) / YELLOW (approval) / RED (operator-only)
- **Zero-cost runnable: **L0+L1 sufficient for basic operation; cloud tiers activated by performance
- **Session/regime awareness: **Asia/Europe/Americas/Weekend + crypto event calendar


# §4 變更路由快速查詢 / Change Routing Quick Reference

When you need to make a change, find it in this table to know which document governs it and what approval is needed.


| **Question** | **Go To** | **Key Content** |
|---|---|---|
| What can the Agent trade? | **DOC-04 §3** | Product family matrix, order types |
| What strategies are available? | **DOC-04 §4** | Strategy library, autonomous scope |
| How are risks controlled? | **EX-01 §2–4** | P0/P1/P2, stops, attention tax |
| Who does what? | **EX-06** | Agent roles, conflict arbitration |
| How does the system learn? | **EX-05** | Pipeline, L1–L5, incubation |
| What changes need approval? | **DOC-06 §3** | GREEN/YELLOW/RED routing tables |
| What data is available? | **EX-07** | Data sources, freshness, access matrix |
| How does compute work? | **DOC-08 + DOC-02 §3** | L0–L2 tiers, trigger conditions |
| When can we go live? | **DOC-04 §11 + DOC-06 §4** | Paper→Live gate: 4wk/500/PnL/30%/Sharpe |
| What are the root rules? | **DOC-01** | 9 root principles + 7 additional articles |

*End of Document — DOC-NAV Governance Document Navigator V3.0 — OpenClaw/Bybit*
