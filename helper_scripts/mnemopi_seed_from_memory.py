#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：把 srv/memory/*.md（跳過 archive/ 與 README.md）seed 進 mnemopi 的
    `tradebot-dev` bank，作為 Mac dev 側 memory 召回索引「試點」。
    MEMORY.md（srv/memory/）永遠是 SSOT；mnemopi 庫只是可隨時整刪重建的衍生召回索引。
主要函數/類：parse_frontmatter / iter_topic_entries / iter_index_entries /
    MnemopiMcpClient（stdio JSON-RPC 2.0 client）/ main。
依賴：純 stdlib（subprocess / json / pathlib / argparse）；外部依賴=全域安裝的
    `mnemopi` CLI（@oh-my-pi/pi-mnemopi@15.11.2，bun runtime）。
硬邊界：
    1. 零網路 — 子進程 env 強制 MNEMOPI_NO_EMBEDDINGS=1（FTS-only，embed() 入口短路）
       + MNEMOPI_LLM_ENABLED=0 + MNEMOPI_HOST_LLM_ENABLED=0，並剝除所有可能讓
       mnemopi 取得外部 API 能力的 key/URL env（防禦縱深：gate 已關，再拿走鑰匙）。
    2. 只寫 ~/.local/share/mnemopi-tradebot/（repo 外），絕不寫 repo / PG / engine。
    3. 重跑語義 = 整個 bank 砍掉重建（衍生品天然冪等）；不嘗試增量去重。
為什麼 seed 粒度是「topic 檔每檔一條 + MEMORY.md 每條索引 bullet 一條」：
    MEMORY.md 整檔餵一條會讓單一巨型文檔在 FTS 上命中幾乎所有查詢、長期佔據 top-k
    污染召回；逐 bullet 才對齊試點判準（PM 召回命中率 vs 純 MEMORY.md 索引逐行掃）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 路徑推算：本檔在 srv/helper_scripts/ → parents[1] = srv（實測驗證，禁硬編 user 路徑）
SRV_ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = SRV_ROOT / "memory"

# 數據目錄在 repo 外（試點退出時 `rm -rf` 整目錄即可）
DATA_DIR = Path.home() / ".local" / "share" / "mnemopi-tradebot"
BANK = "tradebot-dev"

# 不 seed 的檔案：MEMORY.md 另走逐-bullet 路徑；README.md 是目錄結構說明非記憶內容
SKIP_FILES = {"README.md"}
INDEX_FILE = "MEMORY.md"

# 每條 topic 檔記憶的正文摘錄上限（字元）。FTS 召回靠關鍵詞，不需要全文；
# 摘錄過長會稀釋 BM25 權重並拖慢索引。
BODY_EXCERPT_CHARS = 1500

# MEMORY.md 索引 bullet 形如「- [標題](topic_file.md) — 摘要」
INDEX_BULLET_RE = re.compile(r"^- \[(?P<title>.+?)\]\((?P<link>\S+?)\)\s*(?:[—–-]\s*)?(?P<rest>.*)$")


def build_child_env() -> dict[str, str]:
    """構造 mnemopi 子進程環境：FTS-only + 零外連。

    為什麼要剝 key：mnemopi 的 embedApi/callRemoteLlm 雖已被
    MNEMOPI_NO_EMBEDDINGS=1 / 空 MNEMOPI_LLM_BASE_URL 短路，但它的 key 解析會
    fallback 到 OPENROUTER_API_KEY / OPENAI_API_KEY；把鑰匙從子進程拿走，
    即使未來版本 gate 行為漂移也不可能外連成功（防禦縱深）。
    """
    env = dict(os.environ)
    env["MNEMOPI_DATA_DIR"] = str(DATA_DIR)
    env["MNEMOPI_NO_EMBEDDINGS"] = "1"
    env["MNEMOPI_LLM_ENABLED"] = "0"
    env["MNEMOPI_HOST_LLM_ENABLED"] = "0"
    for key in (
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "OPENAI_API_KEY",
        "MNEMOPI_EMBEDDING_API_KEY",
        "MNEMOPI_EMBEDDING_API_URL",
        "MNEMOPI_EMBEDDINGS_VIA_API",
        "MNEMOPI_LLM_API_KEY",
        "MNEMOPI_LLM_BASE_URL",
    ):
        env.pop(key, None)
    return env


def find_mnemopi() -> str:
    """定位 mnemopi 可執行檔；找不到=安裝前置未完成，fail loud。"""
    path = shutil.which("mnemopi") or shutil.which("mnemopi", path="/opt/homebrew/bin")
    if not path:
        sys.exit("ERROR: 找不到 mnemopi CLI（npm install -g @oh-my-pi/pi-mnemopi 未完成？）")
    return path


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """極簡 YAML frontmatter 解析（只取頂層 `key: value` 單行欄位）。

    不引入 PyYAML：memory 檔的 frontmatter 全是平鋪單行欄位（name/description/...），
    縮排的嵌套欄位（如 metadata:）直接跳過即可，stdlib 解析足夠且零依賴。
    回傳 (frontmatter dict, 正文)。無 frontmatter 時 dict 為空、正文=全文。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm: dict[str, str] = {}
    for idx in range(1, len(lines)):
        line = lines[idx]
        if line.strip() == "---":
            return fm, "\n".join(lines[idx + 1 :])
        if line.startswith((" ", "\t")) or ":" not in line:
            continue  # 嵌套欄位或非 key:value 行，跳過
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    # 沒有閉合 '---'：視為無 frontmatter（fail-safe，寧可整檔當正文）
    return {}, text


def body_excerpt(body: str, limit: int = BODY_EXCERPT_CHARS) -> str:
    """取正文要點：去空行後串接，截到 limit 字元。"""
    parts: list[str] = []
    total = 0
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts.append(line)
        total += len(line) + 1
        if total >= limit:
            break
    return "\n".join(parts)[:limit]


def iter_topic_entries() -> list[dict]:
    """topic 檔 → 每檔一條記憶（frontmatter description + 正文摘錄）。"""
    entries: list[dict] = []
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if path.name in SKIP_FILES or path.name == INDEX_FILE:
            continue
        fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = fm.get("name", path.stem)
        desc = fm.get("description", "")
        excerpt = body_excerpt(body)
        content = f"[memory/{path.name}] {title}"
        if desc:
            content += f"\n{desc}"
        if excerpt:
            content += f"\n{excerpt}"
        entries.append(
            {
                "content": content,
                "source": "memory_md_seed",
                "veracity": "stated",
                "importance": 0.5,
                "metadata": {"file": f"memory/{path.name}", "kind": "topic"},
            }
        )
    return entries


def iter_index_entries() -> list[dict]:
    """MEMORY.md 索引 → 每條 bullet 一條記憶（PM 手工壓實的 hot facts，權重略高）。"""
    entries: list[dict] = []
    index_path = MEMORY_DIR / INDEX_FILE
    if not index_path.exists():
        return entries
    for raw in index_path.read_text(encoding="utf-8").splitlines():
        m = INDEX_BULLET_RE.match(raw.strip())
        if not m:
            continue
        title, link, rest = m.group("title"), m.group("link"), m.group("rest")
        content = f"[memory/MEMORY.md → {link}] {title}"
        if rest:
            content += f" — {rest}"
        entries.append(
            {
                "content": content,
                "source": "memory_md_index_seed",
                "veracity": "stated",
                "importance": 0.7,
                "metadata": {"file": "memory/MEMORY.md", "topic_file": link, "kind": "index_bullet"},
            }
        )
    return entries


class MnemopiMcpClient:
    """`mnemopi mcp` stdio JSON-RPC 2.0 極簡 client（newline-delimited）。

    為什麼走 MCP stdio 而非 CLI `mnemopi store`：CLI 不帶 --bank 旗標、只能寫
    default bank；MCP 工具每呼叫帶 bank 參數，能準確落到 tradebot-dev，且單一
    長駐子進程比逐條 spawn CLI（bun 冷啟 ~百 ms × 200 條）快一個量級。
    """

    def __init__(self, mnemopi_bin: str, env: dict[str, str]) -> None:
        self._proc = subprocess.Popen(
            [mnemopi_bin, "mcp", "--bank", BANK],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            bufsize=1,
        )
        self._next_id = 0
        # MCP 慣例：先 initialize 握手
        self.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "mnemopi_seed_from_memory", "version": "1"}})

    def call(self, method: str, params: dict) -> dict:
        assert self._proc.stdin and self._proc.stdout
        self._next_id += 1
        req = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        self._proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("mnemopi mcp 子進程提前結束（stdout EOF）")
        resp = json.loads(line)
        if resp.get("error"):
            raise RuntimeError(f"JSON-RPC error: {resp['error']}")
        return resp["result"]

    def tool(self, name: str, arguments: dict) -> dict:
        """tools/call 並解開 MCP content envelope；isError 視為失敗 fail loud。"""
        result = self.call("tools/call", {"name": name, "arguments": arguments})
        inner = json.loads(result["content"][0]["text"])
        if result.get("isError"):
            raise RuntimeError(f"tool {name} failed: {inner}")
        return inner

    def close(self) -> None:
        if self._proc.stdin:
            self._proc.stdin.close()
        self._proc.wait(timeout=30)


def reset_bank(mnemopi_bin: str, env: dict[str, str]) -> None:
    """整 bank 重建：衍生索引的冪等語義（delete 失敗=bank 不存在，可忽略）。"""
    subprocess.run([mnemopi_bin, "bank", "delete", BANK], env=env, capture_output=True)
    created = subprocess.run([mnemopi_bin, "bank", "create", BANK], env=env, capture_output=True, text=True)
    if created.returncode != 0:
        sys.exit(f"ERROR: bank create 失敗：{created.stdout}{created.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="從 srv/memory/*.md seed mnemopi tradebot-dev bank（衍生召回索引，可整刪重建）")
    # 此腳本只寫 repo 外的本地衍生 SQLite（試點退出=整目錄刪除），無 DB/DSN 寫入
    # 面，故默認直接執行；--dry-run 供只看計數。
    parser.add_argument("--dry-run", action="store_true", help="只列計數，不寫入")
    args = parser.parse_args()

    if not MEMORY_DIR.is_dir():
        sys.exit(f"ERROR: 找不到 memory 目錄：{MEMORY_DIR}")

    topic_entries = iter_topic_entries()
    index_entries = iter_index_entries()
    print(f"topic 檔條目: {len(topic_entries)}")
    print(f"MEMORY.md 索引 bullet 條目: {len(index_entries)}")
    print(f"合計待 seed: {len(topic_entries) + len(index_entries)}")

    if args.dry_run:
        print("[dry-run] 未寫入。")
        return 0

    mnemopi_bin = find_mnemopi()
    env = build_child_env()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    reset_bank(mnemopi_bin, env)

    client = MnemopiMcpClient(mnemopi_bin, env)
    seeded = 0
    failed: list[str] = []
    try:
        for entry in topic_entries + index_entries:
            arguments = {
                "content": entry["content"],
                "source": entry["source"],
                "veracity": entry["veracity"],
                "importance": entry["importance"],
                "metadata": entry["metadata"],
                "bank": BANK,
            }
            try:
                inner = client.tool("mnemopi_remember", arguments)
                if inner.get("status") in ("stored", "updated"):
                    seeded += 1
                else:
                    failed.append(f"{entry['metadata']}: {inner}")
            except RuntimeError as exc:
                failed.append(f"{entry['metadata']}: {exc}")
        stats = client.tool("mnemopi_stats", {"bank": BANK})
    finally:
        client.close()

    print(f"已 seed: {seeded}")
    if failed:
        print(f"失敗 {len(failed)} 條：")
        for item in failed[:10]:
            print(f"  - {item}")
        return 1
    # mnemopi_stats 回應形狀（實測 15.11.2）：{"working": {"total": N}, "episodic": {...}, ...}
    total = stats.get("working", {}).get("total", "?")
    print(f"bank '{BANK}' working memory total: {total}")
    print(f"DB 落盤: {DATA_DIR}/banks/{BANK}/mnemopi.db")
    return 0


if __name__ == "__main__":
    sys.exit(main())
