---
name: 注釋默認只寫中文（2026-05-05 起）
description: Operator 2026-05-05 決定變更 CLAUDE.md §七 bilingual policy — 新代碼注釋默認只寫中文，原有不動，修改時移除英文只保留中文
type: feedback
---

新規（2026-05-05 起）：
- 新建/修改的代碼注釋**只寫中文**（不再強制中英對照）
- 原有中英對照注釋**不主動清理**（保持現狀）
- 修改既有中英對照 block 時**移除英文只保留中文**（當下動到的 block 端用此規則）

範圍：MODULE_NOTE / docstring / inline comment / fail-closed 路徑 / 安全代碼。

**Why:** bilingual mandate 使 runner.rs 等高內聚模組 41% 行是注釋；V055 5-round + R6 W1+W2 共增 ~4000 LOC 注釋，token + LOC 成本顯著。中文足以承載必要語義。

**How to apply:**
1. 派 sub-agent 寫代碼時，dispatch brief 必註明「注釋只寫中文」（避免 sub-agent 自動套舊 bilingual mandate）
2. PM 端寫代碼/migration/test 同樣只寫中文
3. E2 review：注釋僅中文 → PASS；注釋僅英文 → push back（中文是必要層）；既有中英對照 block 不主動清 OK
4. 動到既有 bilingual block 時順手刪英文（最小變動原則：只動 block 內被改的內容，不擴大 scope）

**E2 / agent definition update:** CLAUDE.md §七「雙語注釋（強制）」section 已 retrofit 為「注釋規範（默認中文）」。所有 agent 定義（E2.md / PA.md / E1.md）下次接手需 align — 但暫不 retroactive 改 agent definition file。
