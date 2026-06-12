# Healthcheck Docs

> **REFERENCE ONLY**
>
> 本目录保存 healthcheck 设计和说明，不代表当前 runtime health。当前 runtime
> 状态、passive wait、operator action 和 gate 结果以根目录 `TODO.md` 及最新
> PM/role report 为准。

## 当前文件

| 文件 | 用途 |
|---|---|
| `2026-05-02--lg5_health_checks.md` | LG-5 healthcheck 设计 / 说明。 |
| `2026-05-09--live_pipeline_active_healthcheck.md` | live pipeline active healthcheck 说明。 |

## 使用规则

- 写结论前必须运行或读取最新 healthcheck evidence；不能只引用本目录文档。
- 若 healthcheck 语义变更，更新对应脚本/runner 后再更新这里。
