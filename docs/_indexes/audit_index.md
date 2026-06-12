# Audit Index

> **ROUTER ONLY**
>
> 本索引解释 audit 相关目录的语义，避免把历史审计证据误读成当前 issue
> tracker。当前 active issue tracker 是 GitHub Issues；当前 active queue 是根目录
> `TODO.md`。

## Audit Folders

| 路径 | 语义 | 不要误读成 |
|---|---|---|
| `docs/audit/` | Legacy 62-finding audit bundle、working ledgers、remediation tracking 历史证据。 | 当前 GitHub issue tracker 或 active blocker list。 |
| `docs/audits/` | 按日期保存的专项 audit / verdict / system audit evidence。 | 当前 sign-off 状态；必须看最新 PM/role report。 |
| `docs/governance_dev/audits/` | 治理开发阶段的 round audit 和合规证据。 | 当前治理实现状态。 |
| `docs/CCAgentWorkSpace/*/workspace/reports/` | 角色级审阅、实现、验证和 PM closure 报告。 | 可批量移动的日志堆；这些路径被大量引用。 |

## 读取顺序

1. 先读 `TODO.md` 判断该主题是否仍 active。
2. 再读 `docs/_indexes/initiative_index.md` 找主题入口。
3. 需要历史证据时再进 audit/report/archive 目录。

## 迁移规则

- 现阶段不合并 `docs/audit/` 与 `docs/audits/`。
- 如未来迁移到统一 taxonomy，必须先更新 `docs/_indexes/path_redirects.md`，
  并在旧路径保留 redirect stub。
