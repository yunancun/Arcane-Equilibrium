---
name: Hardware & Storage Infrastructure
description: AMD AI MAX 395 128GB with local LLMs as dominant memory consumer + 40TB NAS via 10GbE
type: project
---

硬件環境：AMD AI MAX 395 · 128GB 統一記憶體 · Ubuntu · NVMe SSD · 40TB NAS (10GbE)

**Why:** 本地 Ollama/LMStudio 是記憶體大戶（Qwen 9B ~18GB / 27B ~54GB），PG 不能搶記憶體。

**How to apply:** 
- PG shared_buffers 必須克制（4-8GB 而非 32GB），讓 OS page cache + LLM 用大頭
- Parquet 長期歸檔可以放 NAS（40TB 足夠 10+ 年）
- 數據庫方案必須把 LLM 記憶體消耗納入 RAM budget
- 10GbE NAS 延遲：Parquet 冷讀取可接受，PG 熱數據必須本地 NVMe
