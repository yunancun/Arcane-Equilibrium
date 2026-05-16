---
name: owasp-checklist
description: OWASP Top 10 (2021) 項目化審計，針對 OpenClaw FastAPI / Rust IPC / PostgreSQL / Bybit REST 的 attack surface 量身。E3 agent 主用。
allowed-tools: Read, Grep, Glob, Bash
---

# OWASP Top 10 Checklist（OpenClaw 專用）

> **優先序**：runtime RiskConfig TOML > Rust schema > `TODO.md` active state / runtime evidence > `README.md` stable surfaces > `CLAUDE.md` operating rules > governance docs > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

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

## OWASP Top 10 (2021) 逐條

### A01 Broken Access Control
- [ ] `/operator/*` 路由 100% 走 Operator 角色守衛（`current_actor()` + role check）
- [ ] 寫操作（POST/PUT/DELETE）不可被 viewer/researcher 角色觸達
- [ ] `live_reserved` global mode 由 Operator 開關，**不可** env var override
- [ ] Decision Lease 寫入需有效 lease + 未過期 + lease.actor == request.actor
- [ ] grep：`@require_role`, `current_actor`, `is_operator`

### A02 Cryptographic Failures
- [ ] `authorization.json` HMAC-SHA256 簽名驗證在 Rust 側強制（`build_exchange_pipeline`）
- [ ] Bybit API key/secret **不入** git；存 `$OPENCLAW_SECRETS_DIR/secret_files/bybit/<slot>/`
- [ ] HTTPS-only 對外（`api.bybit.com`），禁 plain HTTP
- [ ] 不自寫 crypto；用 `hmac` / `cryptography` / Rust `ring`

### A03 Injection
- [ ] **SQL**：100% 用參數化查詢（Python `asyncpg.execute(query, *args)` / Rust sqlx `query!()`）；禁 f-string 拼 SQL
- [ ] **Shell**：`subprocess.run(args=[...])` list form，禁 `shell=True` 拼 user input
- [ ] **Command injection**：bybit symbol 等用戶可控字串入 path 前，正則白名單 `^[A-Z0-9_-]+$`
- [ ] **NoSQL/Redis**：N/A（不用）
- [ ] **Log injection**：log message 不直接內嵌 raw user input；structured log 欄位化

### A04 Insecure Design
- [ ] 寫操作預設 fail-closed（錯誤 → 拒絕 而非通過）
- [ ] `OPENCLAW_ALLOW_MAINNET=1` 必須有 + 憑證雙驗才允 Mainnet
- [ ] Rate limit 在 `slowapi.Limiter` 上對外路由全覆蓋
- [ ] 重要操作 idempotency key（防重放 / 重試）

### A05 Security Misconfiguration
- [ ] FastAPI `debug=False` in prod
- [ ] CORS 不開 `*`；白名單 GUI origin
- [ ] DB user 最小權限（read-only 給 GUI；DDL 給 migration only）
- [ ] systemd unit 不 root 跑（檢 `User=` 行）
- [ ] env var **不寫進** code / log / commit message

### A06 Vulnerable Components
- [ ] Python：`pip-audit` / `safety check` 無 high/critical
- [ ] Rust：`cargo audit` + `cargo deny` 無 RUSTSEC critical
- [ ] requirements.txt + Cargo.lock 鎖版本（重現性）
- [ ] 棄用 unmaintained 依賴（最後 commit > 2y 紅旗）

### A07 Authentication Failures
- [ ] Operator role auth 不存 client-side cookie / localStorage 純文字
- [ ] Live session 5 門控**全綠**才允（`CLAUDE.md` Hard Boundaries）
- [ ] Login attempt 失敗 N 次 → 短期鎖（防爆破）
- [ ] Session token TTL 合理（短，5-15min）+ refresh 流程

### A08 Software/Data Integrity
- [ ] CI/CD pipeline 不允 unsigned tag deploy
- [ ] `helper_scripts/` 內不從 untrusted source `curl | bash`
- [ ] DB migration（V### sql）必 review + 套用 Guard A/B/C
- [ ] Rust binary release build 才上 prod；debug build 留 dev only

### A09 Logging Failures
- [ ] `change_audit_log.py`（DOC-06）append-only JSONL 完整覆蓋寫操作
- [ ] 失敗的 auth attempt 必 log（不只成功）
- [ ] 關鍵風控動作（lease acquire/release、order submit/cancel、risk degrade）落 `audit_persistence`
- [ ] log 不寫敏感（API key / authorization HMAC / Operator password 全脫敏）

### A10 SSRF
- [ ] 任何「外部 URL」可控的路由白名單域名（Bybit-only）
- [ ] Local LLM 路由僅 `127.0.0.1` / `localhost`
- [ ] webhook（如有）拒 `169.254.*` / `127.*` / `10.*` private IP

## OpenClaw 補充項

- [ ] `OPENCLAW_BASE_DIR` / `OPENCLAW_DATA_DIR` / `OPENCLAW_SECRETS_DIR` 不出現用戶 home 字面值（`/home/ncyu`/`/Users/<name>`）
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
