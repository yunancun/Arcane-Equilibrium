---
name: project_2026_06_08_odysseus_mac_deploy
description: Odysseus (PewDiePie self-hosted AI workspace) deployed loopback-only on dev Mac; ssh trade-core depends on Tailscale MagicDNS (no ~/.ssh/config entry)
metadata: 
  node_type: memory
  type: project
  originSessionId: dbbb59a4-3a26-4b45-8688-312dfdd37e49
---

在開發用 Mac（macbook-pro, tailscale `100.77.153.53`, macOS 26 Tahoe/Darwin 25.5）部署了 **Odysseus**（github `pewdiepie-archdaemon/odysseus`，PewDiePie 真帳號的 self-hosted AI workspace，MIT，~58k★，名字嚇人但非冒牌）。與 TradeBot 無關但同機共存。

**位置/執行**：`~/Projects/odysseus`，**native（非 Docker，為了 Metal GPU 本地推理）**。`./start-macos.sh` 啟動（idempotent，re-run 安全）。venv 在 repo 內。brew 裝了 `tmux`/`llama.cpp`/`apfel`(1.5.1 = Apple on-device FoundationModel→OpenAI server)。uvicorn 綁 `127.0.0.1:7860`，apfel `127.0.0.1:11435`。admin 密碼存在 `.env`（chmod 600）`ODYSSEUS_ADMIN_PASSWORD`，auth.json 已生 bcrypt hash。

**安全加固**（operator 三度強調 security／勿動 Tailscale／勿斷 SSH）：自寫 `.env` 綁 `APP_BIND=127.0.0.1`＋`AUTH_ENABLED=true`＋`LOCALHOST_BYPASS=false`＋`ODYSSEUS_SCRIPT_HOST=localhost`。驗證 `nc 100.77.153.53:7860` **refused** = 不在 tailnet 暴露。Odysseus 對 tailscale 只**唯讀**（model_discovery 掃 tailnet 找 LLM server）；app 內 agent 的 bash/file 工具有 sensitive-path deny-list 擋 `~/.ssh`/`id_rsa`/`authorized_keys`（`src/tool_execution.py:163`，`tests/test_tool_path_confinement.py` 驗）。安全審查全綠：無 curl|bash、無 sudo（Mac 路徑）、無 os.system/eval、有 SECURITY.md/THREAT_MODEL.md/2FA/nh3 sanitize。

**關鍵 infra 發現（對 TradeBot 有用）**：**`ssh trade-core` 在 `~/.ssh/config` 無對應 Host 條目 → 靠 Tailscale MagicDNS 解析 `trade-core`→`100.91.109.86`**。即 **Tailscale 斷 = SSH-to-Linux 開發中斷，兩者同一依賴**。動 Tailscale/DNS 前須知此。見 [[project_ssh_bridge_workflow]]。

**現況/持久化**：部署當下 uvicorn 跑在該 CC session 的背景任務內（**session 結束會停**）。要持久：自己 terminal 跑 `cd ~/Projects/odysseus && ./start-macos.sh`，或 `./build-macos-app.sh` 做可點 .app，或 launchd LaunchAgent（尚未設）。停止：`pkill -f 'uvicorn app:app'; pkill -f 'apfel --serve'`。Playwright browser-MCP 為 optional 未裝（`npx -y @playwright/mcp@latest --version` 可補）。

**更新 2026-06-08（clickable app + memory 匯入完成；API key operator 自理）**：
- 可點 app 建好並裝到 `/Applications/Odysseus.app`（`build-macos-app.sh`；其 launcher **只起 uvicorn**，不起 apfel/chroma）。
- **Memory 匯入**：92 Claude `.md`（canonical `-TradeBot/memory`）+ 2 Codex `AGENTS.md`（TradeBot + srv；Codex 本身 memories_1.sqlite 空、AGENTS.md 才是其 memory）→ 複製到 `data/personal_docs/claude-codex-memory/` → 經 `/api/personal/add_directory` 索引。chroma collection `odysseus_rag_fastembed` = **445 vectors**（95 檔，0 failed）。隱私：含交易 IP，雲端模型聊天會送被檢索片段 → 敏感查詢務必用本地模型（apfel/Ollama/llama.cpp）。
- **RAG/vector-memory/tool-index 需要 ChromaDB service**：native `start-macos.sh` **不啟動 chroma** → 預設連 `localhost:8100` 失敗（degraded，503 "RAG not available"）。修法：`~/Projects/odysseus/venv/bin/chroma run --host 127.0.0.1 --port 8100 --path ~/Projects/odysseus/data/chroma`（loopback；本 session 已起背景）。**持久化缺口：chroma+apfel 未 autostart，clickable app 只起 uvicorn → 重開機後 RAG 失效除非 chroma 在跑**；建議裝 chroma LaunchAgent(loopback)。三服務皆 loopback：uvicorn `:7860`、apfel `:11435`、chroma `:8100`。
- **API keys**：operator 選**不重用** TradeBot production key（`secrets/secret_files/ai/gateway_api_keys.env` 內有 OpenAI `sk-proj…`(164) + Anthropic `sk-ant…`(108)，刻意**不接**以隔離 blast radius）；DeepSeek 全機找不到。改由 operator 自行在 UI（Settings→Model Endpoints / `POST /api/model-endpoints` 需 admin）加專用 key：OpenAI `https://api.openai.com/v1`、Anthropic `https://api.anthropic.com/v1`(原生 /messages)、DeepSeek `https://api.deepseek.com/v1`(OpenAI-compat)。endpoint key 存 `data/app.db`(Fernet，master `data/.key` mode600)。Codex=ChatGPT OAuth、Claude Code=OAuth，皆無 raw API key 可抽。
