---
name: 最少确认偏好
description: 用户不想被反复问 yes/no，除非是真正高风险操作才确认
type: feedback
---

不要反复要求用户确认。自主执行大部分操作。

**Why:** 用户觉得频繁确认打断工作流，降低效率。

**How to apply:** 只在以下情况才请求确认：
- git push / git pull
- 删除重要文件或分支
- 其他不可逆的破坏性操作

读文件、写文件、编辑代码、运行测试、创建 commit、git add/diff/log/stash 等日常操作直接执行，不需要确认。
settings.local.json 已配置广泛的 allow 规则 + deny git push/pull。
