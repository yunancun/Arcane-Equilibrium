---
name: owasp-checklist
description: E3 agent 主用：安全審計、PR pre-merge security gate、新增 API 路由/IPC handler/webhook、或改動觸及認證、密鑰、SQL、subprocess 時必讀。
allowed-tools: Read, Grep, Glob, Bash
---

# OWASP Top 10 Checklist（OpenClaw 專用）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：OWASP Top 10 各類別定義與通用防護不在本檔重述；本檔只列本專案的攻擊面映射、專案 gate 與 SSOT 指針。逐條審計時用內建 OWASP 知識展開，以下每類只列 OpenClaw delta。

## 何時觸發

- E3 收到「安全審計」「OWASP 體檢」「PR pre-merge security gate」
- 新增 `/api/v1/*` 路由、Rust IPC handler、外部 webhook
- 接觸密鑰 / authorization / Operator 認證 / Bybit REST 路徑
- 任何 SQL / shell / subprocess / dynamic import 改動

## 攻擊面地圖

| 面 | 主要檔案 | 入口 |
|---|---|---|
| HTTP API | `program_code/.../control_api_v1/app/main_legacy.py` + 5 sibling | uvicorn :8000 |
| Rust IPC | `rust/openclaw_engine/src/ipc/*` | Unix socket |
| DB | PostgreSQL via sqlx (Rust) + asyncpg (Python) | TimescaleDB |
| External | Bybit REST + WS | api.bybit.com / api-demo.bybit.com |
| Local LLM | Ollama / LM Studio | localhost only |

## OWASP 逐條 — OpenClaw delta

### A01 Broken Access Control
- [ ] `/operator/*` 路由 100% 走 Operator 角色守衛（`current_actor()` + role check）；寫操作不可被 viewer/researcher 觸達
- [ ] `live_reserved` global mode 由 Operator 開關，**不可** env var override
- [ ] Decision Lease 寫入需有效 lease + 未過期 + lease.actor == request.actor
- [ ] grep：`@require_role`, `current_actor`, `is_operator`

### A02 Cryptographic Failures
- [ ] `authorization.json` HMAC-SHA256 簽名驗證在 Rust 側強制（`build_exchange_pipeline`）
- [ ] Bybit API key/secret **不入** git；存 `$OPENCLAW_SECRETS_DIR/secret_files/bybit/<slot>/`
- [ ] 不自寫 crypto；用 `hmac` / `cryptography` / Rust `ring`；對外 HTTPS-only

### A03 Injection
- [ ] SQL 100% 參數化（`asyncpg.execute(query, *args)` / sqlx `query!()`）；禁 f-string 拼 SQL；NoSQL/Redis N/A（不用）
- [ ] `subprocess.run(args=[...])` list form，禁 `shell=True` 拼 user input
- [ ] bybit symbol 等用戶可控字串入 path 前，正則白名單 `^[A-Z0-9_-]+$`
- [ ] structured log 欄位化，不直接內嵌 raw user input

### A04 Insecure Design
- [ ] 寫操作預設 fail-closed（錯誤 → 拒絕 而非通過）
- [ ] `OPENCLAW_ALLOW_MAINNET=1` 必須有 + 憑證雙驗才允 Mainnet
- [ ] Rate limit 在 `slowapi.Limiter` 上對外路由全覆蓋；重要操作 idempotency key

### A05 Security Misconfiguration
- [ ] FastAPI `debug=False` in prod；CORS 白名單 GUI origin 不開 `*`
- [ ] DB user 最小權限（read-only 給 GUI；DDL 給 migration only）；systemd unit 不 root 跑
- [ ] env var 不寫進 code / log / commit message

### A06 Vulnerable Components
- [ ] `pip-audit` / `safety check` / `cargo audit` + `cargo deny` 無 high/critical；requirements.txt + Cargo.lock 鎖版本；棄用 unmaintained 依賴（最後 commit > 2y 紅旗）

### A07 Authentication Failures
- [ ] Operator role auth 不存 client-side 純文字
- [ ] Live session 5 門控**全綠**才允（`CLAUDE.md` Hard Boundaries）
- [ ] Login 失敗 N 次短期鎖；session token 短 TTL + refresh

### A08 Software/Data Integrity
- [ ] CI/CD pipeline 不允 unsigned tag deploy
- [ ] `helper_scripts/` 內不從 untrusted source `curl | bash`
- [ ] DB migration（V### sql）必 review + 套用 Guard A/B/C；Rust release build 才上 prod

### A09 Logging Failures
- [ ] `change_audit_log.py`（DOC-06）append-only JSONL 完整覆蓋寫操作
- [ ] 失敗的 auth attempt 必 log；關鍵風控動作（lease acquire/release、order submit/cancel、risk degrade）落 `audit_persistence`
- [ ] log 不寫敏感（API key / authorization HMAC / Operator password 全脫敏）

### A10 SSRF
- [ ] 「外部 URL」可控路由白名單域名（Bybit-only）；Local LLM 路由僅 loopback；webhook 拒 private IP

### A11 LLM/Prompt-Injection（本系統 L2 推理鏈）
- [ ] 外部數據經 tool 結果回流注入 L2 prompt（news / web / UGC）有隔離與標記，不當指令執行
- [ ] L2 輸出未驗證不得直接驅動決策鏈（schema 驗證 + 數值範圍檢查後才入 gate）
- [ ] Ollama / LM Studio 綁定 loopback，非 loopback 綁定 = finding
- [ ] prompt / 推理日誌不嵌入 secret；模型輸出寫 DB 前消毒（長度 / 型別 / 注入字元）
- [ ] L2 推理鏈信任邊界詳見 E3.md scope 條目

## OpenClaw 補充項

- [ ] 跨平台路徑硬編碼（user home 字面值）：grep 配方正本見 `pr-adversarial-review` §3.1
- [ ] `live_reserved`、`execution_authority`、`execution_state` 不被 monkey-patch / runtime override
- [ ] LiveDemo 不因 endpoint 降級（authorization/TTL/風控門控按 Live 嚴格標準）
- [ ] `OPENCLAW_AUTO_MIGRATE=1` opt-in 路徑：guard A/B/C 完整，ambiguous state RAISE

## 輸出格式

```markdown
# E3 OWASP 安全審計 — <topic> · <date>

範圍：<files>
基準：commit `<sha>`

## 摘要
總計 N findings · Critical X / High Y / Medium Z / Low W

## Findings
### [CRIT-01] A03 SQL Injection — <file:line>
**證據**：```代碼片段```
**風險**：<具體攻擊鏈>
**修復**：<具體 fix>
**驗證**：<測試方法>

...
```
