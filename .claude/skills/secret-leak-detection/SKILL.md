---
name: secret-leak-detection
description: 掃描代碼/log/commit 中的 API key、authorization HMAC、密鑰路徑、credential pattern 洩漏。E3 agent 主用，PR pre-merge gate。
allowed-tools: Read, Grep, Glob, Bash
---

# Secret Leak Detection（密鑰洩漏掃描）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- E3 收到「密鑰洩漏掃描」「PR 前安全 gate」「commit history 體檢」
- 任何接觸 `bybit_rest_client*` / `live_auth*` / `authorization*` / `secret_*` 路徑
- 新增 env var / config TOML / log statement
- 部署前最後一道閘

## OpenClaw 已知敏感資產

| 資產 | 位置 | 嚴重 |
|---|---|---|
| Bybit API key/secret | `$OPENCLAW_SECRETS_DIR/secret_files/bybit/<slot>/api_key` + `api_secret` | CRITICAL |
| `authorization.json` | `$OPENCLAW_SECRETS_DIR/<env>/authorization.json` | CRITICAL（HMAC + actor + env_allowed） |
| HMAC signing secret | `$OPENCLAW_SECRETS_DIR/<env>/auth_signing_key` | CRITICAL |
| Operator password hash | DB `auth.operators` table | HIGH |
| Layer 2 Claude API key | env `ANTHROPIC_API_KEY` | HIGH |
| LM Studio / Ollama base URL | env `LM_STUDIO_BASE_URL` / `OLLAMA_BASE_URL` | LOW（localhost） |

## 偵測 Pattern（Grep 指紋）

### Pattern A：硬編碼字串
```
grep -nrE '(api_key|api_secret|password|token|hmac_key|signing_key)\s*=\s*["\047][A-Za-z0-9+/=]{16,}' <path>
```

### Pattern B：高熵 base64 / hex 字串
```
grep -nrE '["\047][A-Fa-f0-9]{32,}["\047]' <path>     # hex (HMAC / sha256)
grep -nrE '["\047][A-Za-z0-9+/]{32,}={0,2}["\047]' <path>  # base64
```

### Pattern C：Bybit 特徵
```
grep -nrE '(bybit.*key|BYBIT_API|bybit_secret)' <path>
grep -nrE 'X-BAPI-(API-KEY|SIGN)' <path>     # header literal
```

### Pattern D：log 中洩漏
```
grep -nrE 'log\.(info|debug|warning|error)\([^)]*(api_key|secret|password|token|authorization)' <path>
grep -nrE 'print\([^)]*(api_key|secret|password|token)' <path>
grep -nrE 'logger\.[a-z]+\([^)]*request\.headers' <path>     # 整個 headers 入 log
```

### Pattern E：env var 寫入 log / response
```
grep -nrE '(os\.environ|env::var)\([^)]*(KEY|SECRET|PASSWORD|TOKEN)' <path>
```

### Pattern F：commit message / docstring
```
git log --all -p | grep -E '(api_key|api_secret|hmac|authorization).*=.*["\047][A-Za-z0-9]{20,}'
```

### Pattern G：跨平台路徑硬編碼（順帶查）
```
grep -nrE '(/home/ncyu|/Users/[^/]+)/.*(secret|auth|key)' <path>
```

## 假陽性過濾

允許出現的 token-like 字串：
- 測試 fixture 明標 `# pragma: allowlist secret` 或 `# noqa: secret`
- `tests/` 下 mock value（如 `"test_key_abc123"`）
- 文檔 `docs/` 內範例（明確標 example）
- git hash / commit sha（40 hex chars）

## OpenClaw 必驗白名單

```
✅ 允許：read_secret_from_file(slot_path)
✅ 允許：os.environ["OPENCLAW_SECRETS_DIR"] / Path 拼接
✅ 允許：authorization.json 路徑變數，但 HMAC 內容絕不入 log
❌ 禁：from settings import BYBIT_API_KEY  ← 全局 import
❌ 禁：log.info(f"loaded key {api_key[:8]}...")  ← 即使前綴也算洩漏
❌ 禁：response = {"key": api_key}  ← 任何回 client 的 dict
❌ 禁：commit message / PR description 含真實 key 片段
```

## CI/Pre-commit 整合建議

- `gitleaks` + `truffleHog` + `detect-secrets` 三選一裝 pre-commit
- pre-merge：`pip-audit` + `cargo audit` 同跑
- daily：`git log --all -p | gitleaks detect --pipe`

## 緊急應對（confirmed leak）

1. **立刻**：rotate 該 key（Bybit 後台撤銷 + 生新 key）
2. force-push 不**清** git history（已洩漏視為公開）
3. `git filter-repo` 清史 + 通知所有 fork
4. 寫 incident report（DOC-08 §12 incident path）

## 輸出格式

```markdown
# E3 密鑰洩漏掃描 — <scope> · <date>

範圍：<files / commit range>
工具：grep + 手檢

## 結果
- CRITICAL：N
- HIGH：N
- MEDIUM：N
- 假陽性已剔：N

## CRITICAL Findings
### [LEAK-01] Bybit API key 硬編碼 — <file:line>
證據：`api_key = "AbCdEf..."`
歷史：git blame `<sha>` 引入
建議：
1. 移走 → secret_files
2. rotate Bybit key（已聯絡 operator）
3. git history 清除（filter-repo）
```
