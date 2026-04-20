---
name: 跨平台兼容性強制準則
description: 項目必須隨時可部署在 macOS。路徑不硬編碼/LLM抽象乾淨/服務可遷移/依賴管理乾淨。E2強制審查。
type: feedback
---

項目必須隨時可以部署在 macOS 上運行（計劃從 Ubuntu 遷移到 Mac Studio）。

**Why:** Operator 計劃未來遷移到 Mac Studio M5 Ultra（72B+7B×3+32B 本地推理）。所有代碼必須跨平台。

**How to apply:**
1. 路徑用 `os.environ` 或 `Path(__file__).parent`，禁止 `/home/ncyu/`
2. LLM 調用走 `LocalLLMClient` ABC，不直接調 Ollama HTTP
3. 服務部署不依賴 systemd-specific 特性
4. `requirements.txt` 同步更新，Linux-only 依賴加平台守衛
5. E2 審查必查以上 4 條
6. 跨平台審計（XP-1~4）優先於所有 Phase 0-3 開發
