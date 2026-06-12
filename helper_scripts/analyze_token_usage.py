#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途:解析 Claude Code session transcript,按「主會話 / 各 subagent」分桶統計
    input / output / cache_creation / cache_read token 用量與估算成本;支援多 session
    批次分析,輸出每 session 明細、全 session 合計、按 agentType 聚合 top-N。
主要函數:_scan_transcript(單 transcript 去重累計)/ analyze_session(主會話 +
    subagents/agent-*.jsonl 分桶)/ resolve_session_files(session 定位)/ main(CLI)。
依賴:純標準庫(json / argparse / pathlib / collections / unicodedata),零第三方依賴。
硬邊界:唯讀 transcript,不寫任何狀態或檔案;壞 jsonl 行與缺欄位 fail-open 跳過並
    計數報告(bad_json / missing_usage),絕不因單行損壞中斷整體統計。

出處與授權:改編自 obra/superpowers `tests/claude-code/analyze-token-usage.py`
    (MIT License, Copyright (c) 2025 Jesse Vincent)。
    pin:repo HEAD 6fd4507659784c351abbd2bc264c7162cfd386dc(2026-05-29 評估快照),
    該檔最後變更 commit 991e9d4de93b17ee08646a8115e3f9f88dad2208。

與源腳本的三個行為偏差(皆由本機 transcript 實測驅動,2026-06-11):
  1) message.id 去重(last-wins):同一 assistant 訊息(多 content block 流式寫入)
     會被寫成多行、每行重複攜帶 usage(實測某主會話 202 行只有 61 個唯一
     message.id,逐行累加超計 ~3.3x);且 agent transcript 內同 id 各行
     output_tokens 流式遞增,最後一行才是終值 → 按 message.id 去重、取最後出現。
  2) subagent 用量以 subagents/agent-*.jsonl 為權威:源腳本用主會話
     toolUseResult.usage 當 subagent 總量,實測那只是該 subagent「最後一次
     API call」的 usage(嚴重低估;且被中斷的後台 agent 沒有 toolUseResult,
     只留 transcript 檔)。toolUseResult 僅在 agent transcript 檔缺失時作下限
     fallback(輸出行以 ≈ 前綴標記)。
  3) cache-aware 成本估算:源腳本把 cache token 全價計入 input;本版按標準乘數
     cache write = 1.25x、cache read = 0.1x input 基準費率估算(費率可參數覆蓋;
     僅供相對比較的粗估,不分模型階,非帳單口徑)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# token 分桶欄位(api_calls 另計)
_FIELDS = ("input_tokens", "output_tokens", "cache_creation", "cache_read")

# 成本估算乘數:cache write / read 相對 input 基準費率(Anthropic 標準計價結構)
_CACHE_WRITE_MULT = 1.25
_CACHE_READ_MULT = 0.10

# 表格欄寬(display width;CJK 算 2)
_ID_W = 19
_LABEL_W = 38
_NUM_W = 11
_CACHE_W = 14
_TABLE_W = _ID_W + _LABEL_W + 7 + _NUM_W * 2 + _CACHE_W * 2 + 10


# ---------------------------------------------------------------------------
# 解析層(全部 fail-open:單行 / 單欄位損壞只計數,不中斷)
# ---------------------------------------------------------------------------

def _as_int(value) -> int:
    """fail-open 整數轉換:None / 非數值一律當 0,不讓單一欄位毀掉整行統計。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _cache_creation_tokens(usage: dict) -> int:
    """取 cache 寫入 token:優先 scalar 欄位,缺席時退 nested cache_creation dict 求和。"""
    v = usage.get("cache_creation_input_tokens")
    if v is not None:
        return _as_int(v)
    nested = usage.get("cache_creation")
    if isinstance(nested, dict):
        return sum(_as_int(x) for x in nested.values())
    return 0


def _usage_row(usage: dict) -> tuple[int, int, int, int]:
    """usage dict → (input, output, cache_creation, cache_read) 四元組。"""
    return (
        _as_int(usage.get("input_tokens")),
        _as_int(usage.get("output_tokens")),
        _cache_creation_tokens(usage),
        _as_int(usage.get("cache_read_input_tokens")),
    )


def _empty_bucket() -> dict:
    bucket = {field: 0 for field in _FIELDS}
    bucket["api_calls"] = 0
    return bucket


def _add_bucket(dst: dict, src: dict) -> None:
    for field in _FIELDS:
        dst[field] += src[field]
    dst["api_calls"] += src["api_calls"]


def _iter_jsonl(path: Path, health: dict):
    """逐行 yield 解析成功的 dict;壞行 / 非 dict 行 fail-open 計入 health['bad_json']。"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                health["bad_json"] += 1
                continue
            if not isinstance(obj, dict):
                health["bad_json"] += 1
                continue
            yield obj


def _scan_transcript(path: Path, health: dict, tool_results: dict | None = None) -> dict:
    """
    掃描一個 transcript(主會話或 agent 檔),回傳去重後的 usage bucket。

    為什麼去重:同一 message.id 會被寫成多行(流式 content block),且 agent 檔內
    output_tokens 逐行遞增——取「最後出現」的 usage 才是該次 API call 終值
    (MODULE_NOTE 偏差 1)。message.id 缺失時退該行自身 uuid(不跨行去重,
    誠實多計一行勝過靜默漏計)。

    tool_results 非 None 時(主會話)順帶收集 toolUseResult:
    agentId → 末次 call usage 與 agentType / prompt / status 中繼資料。
    """
    per_message: dict[str, tuple[int, int, int, int]] = {}
    for seq, obj in enumerate(_iter_jsonl(path, health), 1):
        obj_type = obj.get("type")
        if obj_type == "assistant":
            msg = obj.get("message")
            if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                health["missing_usage"] += 1
                continue
            mid = msg.get("id") or obj.get("uuid") or f"line-{seq}"
            per_message[str(mid)] = _usage_row(msg["usage"])
        elif tool_results is not None and obj_type == "user":
            tr = obj.get("toolUseResult")
            if (
                isinstance(tr, dict)
                and tr.get("agentId")
                and isinstance(tr.get("usage"), dict)
            ):
                tool_results[str(tr["agentId"])] = {
                    "usage_row": _usage_row(tr["usage"]),
                    "agent_type": tr.get("agentType"),
                    "prompt": tr.get("prompt") or "",
                    "status": tr.get("status"),
                }
    bucket = _empty_bucket()
    for row in per_message.values():
        for field, value in zip(_FIELDS, row):
            bucket[field] += value
    bucket["api_calls"] = len(per_message)
    return bucket


def _read_agent_meta(meta_path: Path) -> dict:
    """讀 agent-*.meta.json(agentType / description):fail-open,缺檔壞檔回空 dict。"""
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def _first_line(text: str) -> str:
    """取 prompt 首行當 description fallback(沿用源腳本的 'You are ' 前綴剝除)。"""
    line = text.split("\n", 1)[0].strip() if text else ""
    if line.startswith("You are "):
        line = line[len("You are "):]
    return line


def analyze_session(session_file: Path) -> dict:
    """
    分析單一 session:主會話 bucket + 每個 subagent bucket。

    subagent 權威來源 = <session-id>/subagents/agent-*.jsonl 直接解析
    (MODULE_NOTE 偏差 2);主會話 toolUseResult 只補「有結果但無 transcript 檔」
    的 agent(末次 call 下限估計,source='last_call_only')。
    """
    health = {"bad_json": 0, "missing_usage": 0}
    tool_results: dict[str, dict] = {}
    main_bucket = _scan_transcript(session_file, health, tool_results)

    agents: list[dict] = []
    seen_ids: set[str] = set()
    subagents_dir = session_file.parent / session_file.stem / "subagents"
    if subagents_dir.is_dir():
        for agent_file in sorted(subagents_dir.glob("agent-*.jsonl")):
            agent_id = agent_file.stem[len("agent-"):]
            seen_ids.add(agent_id)
            bucket = _scan_transcript(agent_file, health)
            meta = _read_agent_meta(
                agent_file.with_name(agent_file.stem + ".meta.json")
            )
            tr = tool_results.get(agent_id) or {}
            agents.append({
                "agent_id": agent_id,
                "agent_type": meta.get("agentType") or tr.get("agent_type") or "unknown",
                "description": meta.get("description") or _first_line(tr.get("prompt", "")),
                "bucket": bucket,
                "source": "transcript",
            })

    # fallback:主會話有 toolUseResult 但 subagents/ 無對應 transcript 檔。
    # 該 usage 只是末次 call,輸出標 ≈ 表「下限估計」,絕不與 transcript 雙重計數。
    fallback_count = 0
    for agent_id, tr in sorted(tool_results.items()):
        if agent_id in seen_ids:
            continue
        fallback_count += 1
        bucket = _empty_bucket()
        for field, value in zip(_FIELDS, tr["usage_row"]):
            bucket[field] += value
        bucket["api_calls"] = 1
        agents.append({
            "agent_id": agent_id,
            "agent_type": tr.get("agent_type") or "unknown",
            "description": _first_line(tr.get("prompt", "")),
            "bucket": bucket,
            "source": "last_call_only",
        })
    health["fallback_agents"] = fallback_count

    return {
        "session_id": session_file.stem,
        "file": session_file,
        "mtime": session_file.stat().st_mtime,
        "main": main_bucket,
        "agents": agents,
        "health": health,
    }


# ---------------------------------------------------------------------------
# 成本估算
# ---------------------------------------------------------------------------

def estimate_cost_usd(bucket: dict, input_rate: float, output_rate: float) -> float:
    """粗估成本(USD):cache write/read 按乘數折算(MODULE_NOTE 偏差 3)。"""
    return (
        bucket["input_tokens"] * input_rate
        + bucket["cache_creation"] * input_rate * _CACHE_WRITE_MULT
        + bucket["cache_read"] * input_rate * _CACHE_READ_MULT
        + bucket["output_tokens"] * output_rate
    ) / 1_000_000.0


# ---------------------------------------------------------------------------
# 輸出層(display-width 對齊:含中文 description 時仍維持表格欄位)
# ---------------------------------------------------------------------------

def _disp_width(s: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s
    )


def _trunc(s: str, width: int) -> str:
    if _disp_width(s) <= width:
        return s
    out: list[str] = []
    w = 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > width - 1:
            break
        out.append(ch)
        w += cw
    return "".join(out) + "…"


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _disp_width(s))


def _fmt_row(row_id: str, label: str, bucket: dict, cost: float) -> str:
    return (
        _pad(_trunc(row_id, _ID_W - 1), _ID_W)
        + _pad(_trunc(label, _LABEL_W - 1), _LABEL_W)
        + f"{bucket['api_calls']:>7,}"
        + f"{bucket['input_tokens']:>{_NUM_W},}"
        + f"{bucket['output_tokens']:>{_NUM_W},}"
        + f"{bucket['cache_creation']:>{_CACHE_W},}"
        + f"{bucket['cache_read']:>{_CACHE_W},}"
        + f"{cost:>10.2f}"
    )


def _print_table_header() -> None:
    print(
        _pad("bucket", _ID_W)
        + _pad("label", _LABEL_W)
        + f"{'calls':>7}"
        + f"{'input':>{_NUM_W}}"
        + f"{'output':>{_NUM_W}}"
        + f"{'cache_write':>{_CACHE_W}}"
        + f"{'cache_read':>{_CACHE_W}}"
        + f"{'est_usd':>10}"
    )
    print("-" * _TABLE_W)


def print_session_report(report: dict, input_rate: float, output_rate: float) -> None:
    mtime = datetime.fromtimestamp(report["mtime"]).strftime("%Y-%m-%d %H:%M")
    print("=" * _TABLE_W)
    print(f"Session {report['session_id']}")
    print(f"  mtime {mtime} | subagents {len(report['agents'])}")
    print("-" * _TABLE_W)
    _print_table_header()

    main_bucket = report["main"]
    print(_fmt_row(
        "main", "主會話 (coordinator)", main_bucket,
        estimate_cost_usd(main_bucket, input_rate, output_rate),
    ))

    session_total = _empty_bucket()
    _add_bucket(session_total, main_bucket)
    # 按估算成本降序列出 subagent(最貴的先看到)
    ranked = sorted(
        report["agents"],
        key=lambda a: estimate_cost_usd(a["bucket"], input_rate, output_rate),
        reverse=True,
    )
    for agent in ranked:
        _add_bucket(session_total, agent["bucket"])
        prefix = "≈" if agent["source"] == "last_call_only" else ""
        label = f"{prefix}[{agent['agent_type']}] {agent['description']}"
        print(_fmt_row(
            agent["agent_id"], label, agent["bucket"],
            estimate_cost_usd(agent["bucket"], input_rate, output_rate),
        ))

    print("-" * _TABLE_W)
    print(_fmt_row(
        "session total", "", session_total,
        estimate_cost_usd(session_total, input_rate, output_rate),
    ))
    h = report["health"]
    print(
        f"  parse health: bad_json={h['bad_json']} "
        f"missing_usage={h['missing_usage']} "
        f"fallback_agents={h['fallback_agents']}"
        + ("(≈ 行=僅末次 call 的下限估計)" if h["fallback_agents"] else "")
    )
    print()


def print_aggregate(
    reports: list[dict], top_n: int, input_rate: float, output_rate: float
) -> None:
    """全 session 合計 + 按 agentType 聚合 top-N(依估算成本降序)。"""
    grand = _empty_bucket()
    by_type: dict[str, dict] = defaultdict(lambda: {"bucket": _empty_bucket(), "runs": 0})
    for report in reports:
        _add_bucket(grand, report["main"])
        _add_bucket(by_type["main"]["bucket"], report["main"])
        by_type["main"]["runs"] += 1
        for agent in report["agents"]:
            _add_bucket(grand, agent["bucket"])
            entry = by_type[agent["agent_type"]]
            _add_bucket(entry["bucket"], agent["bucket"])
            entry["runs"] += 1

    total_input_incl_cache = (
        grand["input_tokens"] + grand["cache_creation"] + grand["cache_read"]
    )
    total_tokens = total_input_incl_cache + grand["output_tokens"]
    grand_cost = estimate_cost_usd(grand, input_rate, output_rate)

    print("=" * _TABLE_W)
    print(f"全 session 合計({len(reports)} 個 session)")
    print("-" * _TABLE_W)
    print(f"  API calls:               {grand['api_calls']:,}")
    print(f"  input tokens:            {grand['input_tokens']:,}")
    print(f"  output tokens:           {grand['output_tokens']:,}")
    print(f"  cache creation tokens:   {grand['cache_creation']:,}")
    print(f"  cache read tokens:       {grand['cache_read']:,}")
    print(f"  total input (incl cache): {total_input_incl_cache:,}")
    print(f"  total tokens:             {total_tokens:,}")
    print(
        f"  估算成本: ${grand_cost:.2f}"
        f"(基準 ${input_rate:g}/${output_rate:g} per MTok;"
        f"cache write {_CACHE_WRITE_MULT}x / read {_CACHE_READ_MULT}x;粗估非帳單)"
    )
    print()
    print(f"按 agentType 聚合 top-{top_n}(依估算成本降序;main=主會話)")
    print("-" * _TABLE_W)
    _print_table_header()
    ranked = sorted(
        by_type.items(),
        key=lambda kv: estimate_cost_usd(kv[1]["bucket"], input_rate, output_rate),
        reverse=True,
    )
    for agent_type, entry in ranked[:top_n]:
        print(_fmt_row(
            agent_type,
            f"{entry['runs']} run(s)",
            entry["bucket"],
            estimate_cost_usd(entry["bucket"], input_rate, output_rate),
        ))
    if len(ranked) > top_n:
        print(f"  …其餘 {len(ranked) - top_n} 類(用 --top 調整)")
    print("=" * _TABLE_W)


# ---------------------------------------------------------------------------
# session 定位
# ---------------------------------------------------------------------------

def default_transcript_dir() -> Path:
    """
    推導本專案的 Claude Code transcript 目錄:
    ~/.claude/projects/<專案根絕對路徑編碼名>(Claude Code 把 cwd 路徑中
    非英數字元折成 '-')。

    為什麼動態推導:跨平台紅線禁止把使用者絕對路徑硬編進腳本;本檔位於
    <專案根>/srv/helper_scripts/,parents[2] 即 session cwd 所在的專案根,
    在本機解析結果與任務指定的默認目錄一致,搬到其他機器/使用者亦自動成立。
    """
    project_root = Path(__file__).resolve().parents[2]
    encoded = re.sub(r"[^A-Za-z0-9-]", "-", str(project_root))
    return Path.home() / ".claude" / "projects" / encoded


def resolve_session_files(tokens: list[str], tdir: Path, recent: int) -> list[Path]:
    """token(路徑 / UUID / UUID 前綴)→ session jsonl;無 token 時取 mtime 最近 N 個。"""
    if tokens:
        resolved: list[Path] = []
        for token in tokens:
            p = Path(token).expanduser()
            if p.is_file():
                resolved.append(p)
                continue
            name = token if token.endswith(".jsonl") else token + ".jsonl"
            candidate = tdir / name
            if candidate.is_file():
                resolved.append(candidate)
                continue
            matches = sorted(tdir.glob(token + "*.jsonl"))
            if len(matches) == 1:
                resolved.append(matches[0])
                continue
            if not matches:
                raise ValueError(f"找不到 session:{token}(目錄 {tdir})")
            raise ValueError(
                f"session 前綴不唯一:{token} 命中 {len(matches)} 個:"
                + ", ".join(m.stem for m in matches[:5])
            )
        return resolved
    files = sorted(tdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[: max(1, recent)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "分析 Claude Code session transcript 的 token 用量"
            "(主會話 / subagent 分桶 + 全 session 合計 + 按 agentType 聚合)。"
            "唯讀,不寫任何狀態。"
        ),
    )
    parser.add_argument(
        "sessions", nargs="*",
        help="session UUID / UUID 前綴 / .jsonl 路徑;省略時取最近 --recent 個",
    )
    parser.add_argument(
        "--dir", default=None,
        help="transcript 目錄(默認:本專案對應的 ~/.claude/projects/<編碼名>)",
    )
    parser.add_argument(
        "--recent", type=int, default=1,
        help="未指定 session 時,分析 mtime 最近的 N 個 session(默認 1)",
    )
    parser.add_argument(
        "--top", type=int, default=10,
        help="按 agentType 聚合表的 top-N(默認 10)",
    )
    parser.add_argument(
        "--input-rate", type=float, default=3.0,
        help="input 基準費率 USD/MTok(估算用,默認 3.0)",
    )
    parser.add_argument(
        "--output-rate", type=float, default=15.0,
        help="output 費率 USD/MTok(估算用,默認 15.0)",
    )
    args = parser.parse_args(argv)

    tdir = Path(args.dir).expanduser() if args.dir else default_transcript_dir()
    if not tdir.is_dir():
        print(
            f"transcript 目錄不存在:{tdir}\n"
            "請用 --dir 指定 Claude Code 專案 transcript 目錄。",
            file=sys.stderr,
        )
        return 1

    try:
        files = resolve_session_files(args.sessions, tdir, args.recent)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not files:
        print(f"目錄內沒有 session jsonl:{tdir}", file=sys.stderr)
        return 1

    reports: list[dict] = []
    for session_file in files:
        try:
            reports.append(analyze_session(session_file))
        except OSError as exc:
            # fail-open:單一 session 不可讀(權限/競態)跳過,不毀整批
            print(f"跳過不可讀 session {session_file.name}:{exc}", file=sys.stderr)
    if not reports:
        print("沒有任何 session 解析成功。", file=sys.stderr)
        return 1

    for report in reports:
        print_session_report(report, args.input_rate, args.output_rate)
    print_aggregate(reports, max(1, args.top), args.input_rate, args.output_rate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
