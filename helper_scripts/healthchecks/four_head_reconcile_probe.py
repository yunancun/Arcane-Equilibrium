#!/usr/bin/env python3
"""四頭 head 對賬只讀探針（schema ``four_head_reconcile_v1``）。

四頭定義：
  1. Mac HEAD          —— 本機 ``git rev-parse HEAD``。
  2. 真 remote head    —— ``git ls-remote origin refs/heads/main``（不動本地
     ref；離線時 fallback 本地 ``origin/main`` 並標 ``stale_possible``）。
  3. Linux HEAD        —— ssh 遠端 ``git -C <remote-root> rev-parse HEAD``
     （順帶取遠端 ``origin/main``）。
  4. engine build_sha  —— 遠端 ``pgrep -f 'openclaw-engine'``（注意連字符實名，
     勿用 ``-x openclaw_engine``；候選 PID 逐一以 ``/proc/<pid>/comm`` 驗證，
     剔除 pgrep -f 的自我命中）→ 讀 ``/proc/<pid>/environ`` 解析
     ``OPENCLAW_DATA_DIR`` 得真 data dir（**絕不默認 /tmp/openclaw**——實測該處
     有 stale boot_history 會給錯誤 build_sha；解析不到即 fail-close 拒讀）→ 讀
     ``<data_dir>/boot_history.jsonl`` 最後一筆帶 build_sha 的引擎紀錄。同檔
     順帶回報 control_api ``repo_head``（零成本滿足 TODO
     ``P2-RUNTIME-SOURCE-BUILD-PIN-DRIFT-HYGIENE-2026-07-07`` 的 packet 驗收面）。

分類（Mac 側 ``git merge-base --is-ancestor``）：
  - ``ALL_FOUR_SYNC``：四頭全等。
  - ``GIT_SYNC_ENGINE_ANCESTOR``（base class）：三 git 頭同步、engine build 為其
    ancestor；再依 gap 是否觸及 rust/ 非豁免面細分——
      * ``HALF_DEPLOY_REBUILD_REQUIRED``：gap 含 rust/ 非豁免變更（需 rebuild）。
      * ``SOURCE_ONLY_DRIFT``：gap 全為非 rust 或豁免面（source-only 同步即可）。
    豁免面判準 **import** ``cost_gate_learning_lane.standing_envelope_post_
    approval_drift_gate.classify_post_approval_path``（= ``source_generation.py``
    宣告的唯一豁免正本；本檔禁止出現第二份豁免表）。
  - ``MAC_BEHIND_ORIGIN`` / ``LINUX_BEHIND_ORIGIN``：對應頭落後真 remote head。
  - ``INDETERMINATE``：任何事實缺失 / 不可解析 / 非 ancestor 拓撲——一律
    fail-close，不猜。

硬邊界（絕不鬆動）：只讀 git / ssh / proc / 檔案；不 fetch、不 pull、不
rebuild、不 restart、不寫 PG、不下單、不碰 crontab/env/risk/Cost Gate。
唯一本地寫 = 顯式 ``--json-output``。

CLI：``--ssh-host trade-core --remote-repo-root /home/ncyu/BybitOpenClaw/srv``
（默認沿 ``deploy/runtime_source_remote_reconcile_probe.py`` 慣例）、``--human``、
``--fail-on-drift``（非 ALL_FOUR_SYNC → exit 3）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol


SCHEMA_VERSION = "four_head_reconcile_v1"
BOUNDARY = (
    "read-only git/ssh/proc/file probe with optional local JSON artifact write; "
    "no fetch/pull/rebuild/restart, no PG write, no order, no crontab/env/risk/"
    "Cost Gate mutation"
)
ENGINE_COMM = "openclaw-engine"


class RemoteHostClient(Protocol):
    """遠端（Linux runtime）只讀 client 介面；測試以 local fixture 注入。"""

    def git_text(self, args: list[str]) -> str | None: ...

    def pgrep_engine(self) -> list[int]: ...

    def read_comm(self, pid: int) -> str | None: ...

    def read_environ(self, pid: int) -> bytes | None: ...

    def read_text_file(self, path: str) -> str | None: ...


class SshHostClient:
    """SSH 只讀 client。所有 remote command 都是 git / pgrep / proc / cat read。"""

    def __init__(self, ssh_host: str, remote_repo_root: str, *, timeout: int = 30) -> None:
        self.ssh_host = ssh_host
        self.remote_repo_root = remote_repo_root
        self.timeout = timeout

    def _run(self, command: str) -> subprocess.CompletedProcess[bytes] | None:
        try:
            return subprocess.run(
                ["ssh", self.ssh_host, command],
                check=False,
                capture_output=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def git_text(self, args: list[str]) -> str | None:
        quoted = " ".join(shlex.quote(a) for a in args)
        proc = self._run(f"git -C {shlex.quote(self.remote_repo_root)} {quoted}")
        if proc is None or proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="replace").strip()

    def pgrep_engine(self) -> list[int]:
        # pgrep -f 會命中自身 ssh shell（command line 含 pattern），由 read_comm 過濾。
        proc = self._run(f"pgrep -f {shlex.quote(ENGINE_COMM)}")
        if proc is None or proc.returncode != 0:
            return []
        pids: list[int] = []
        for line in proc.stdout.decode("ascii", errors="replace").split():
            try:
                pids.append(int(line))
            except ValueError:
                continue
        return pids

    def read_comm(self, pid: int) -> str | None:
        proc = self._run(f"cat /proc/{int(pid)}/comm")
        if proc is None or proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="replace").strip()

    def read_environ(self, pid: int) -> bytes | None:
        proc = self._run(f"cat /proc/{int(pid)}/environ")
        if proc is None or proc.returncode != 0:
            return None
        return proc.stdout

    def read_text_file(self, path: str) -> str | None:
        proc = self._run(f"cat {shlex.quote(path)}")
        if proc is None or proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="replace")


class LocalFixtureClient:
    """測試/開發用 fixture client：本地 git repo 模擬 Linux checkout，
    dict 模擬 proc/檔案面。記錄被讀過的檔案路徑供測試斷言（如：stale
    /tmp/openclaw 絕不被讀）。"""

    def __init__(
        self,
        repo_root: Path,
        *,
        pids: list[int] | None = None,
        comm_by_pid: dict[int, str] | None = None,
        environ_by_pid: dict[int, bytes] | None = None,
        files: dict[str, str] | None = None,
        git_available: bool = True,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.pids = list(pids or [])
        self.comm_by_pid = dict(comm_by_pid or {})
        self.environ_by_pid = dict(environ_by_pid or {})
        self.files = dict(files or {})
        self.git_available = git_available
        self.read_file_paths: list[str] = []

    def git_text(self, args: list[str]) -> str | None:
        if not self.git_available:
            return None
        proc = subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            check=False,
            capture_output=True,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="replace").strip()

    def pgrep_engine(self) -> list[int]:
        return list(self.pids)

    def read_comm(self, pid: int) -> str | None:
        return self.comm_by_pid.get(pid)

    def read_environ(self, pid: int) -> bytes | None:
        return self.environ_by_pid.get(pid)

    def read_text_file(self, path: str) -> str | None:
        self.read_file_paths.append(path)
        return self.files.get(path)


# ---------------------------------------------------------------------------
# 本地（Mac 側）git helpers
# ---------------------------------------------------------------------------


def _local_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )


def _local_git_text(repo: Path, args: list[str]) -> str | None:
    proc = _local_git(repo, args)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _expand_commit(repo: Path, sha_or_ref: str) -> str | None:
    """把（可能為短前綴的）sha/ref 展開為本地 full commit sha；解不開 → None。"""
    if not sha_or_ref or sha_or_ref == "unknown":
        return None
    return _local_git_text(repo, ["rev-parse", "--verify", f"{sha_or_ref}^{{commit}}"])


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool | None:
    """``git merge-base --is-ancestor``：rc 0=True / 1=False / 其他=None（fail-close）。"""
    proc = _local_git(repo, ["merge-base", "--is-ancestor", ancestor, descendant])
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def resolve_true_remote_head(repo: Path, *, timeout: int = 20) -> dict[str, Any]:
    """真 remote head：``git ls-remote origin refs/heads/main``（不動本地 ref）。

    離線/失敗 → fallback 本地 ``origin/main`` 並標 ``stale_possible=True``。
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-remote", "origin", "refs/heads/main"],
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None and proc.returncode == 0:
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if out:
            sha = out.split()[0]
            return {"sha": sha, "source": "ls_remote", "stale_possible": False}
    fallback = _local_git_text(repo, ["rev-parse", "origin/main"])
    return {"sha": fallback, "source": "local_origin_main_fallback", "stale_possible": True}


# ---------------------------------------------------------------------------
# 遠端 engine 事實（proc + boot_history）
# ---------------------------------------------------------------------------


def _parse_environ_data_dir(environ: bytes) -> str | None:
    for chunk in environ.split(b"\0"):
        if chunk.startswith(b"OPENCLAW_DATA_DIR="):
            value = chunk[len(b"OPENCLAW_DATA_DIR=") :].decode("utf-8", errors="replace").strip()
            return value or None
    return None


def resolve_engine_facts(client: RemoteHostClient) -> dict[str, Any]:
    """engine build_sha + control_api repo_head（fail-close，絕不默認 /tmp/openclaw）。"""
    facts: dict[str, Any] = {
        "engine_pid": None,
        "data_dir": None,
        "boot_history_path": None,
        "engine_build_sha_raw": None,
        "engine_boot_ts": None,
        "engine_binary_path": None,
        "control_api_repo_head": None,
        "errors": [],
    }
    candidates = [
        pid for pid in client.pgrep_engine() if client.read_comm(pid) == ENGINE_COMM
    ]
    if not candidates:
        facts["errors"].append("engine_process_not_found")
        return facts
    if len(candidates) > 1:
        # 多個同名引擎進程 = 拓撲異常，fail-close 不挑（挑錯 PID 會給錯 build_sha）。
        facts["errors"].append(f"multiple_engine_processes:{candidates}")
        return facts
    pid = candidates[0]
    facts["engine_pid"] = pid

    environ = client.read_environ(pid)
    if environ is None:
        facts["errors"].append("engine_environ_unreadable")
        return facts
    data_dir = _parse_environ_data_dir(environ)
    if not data_dir:
        # 絕不默認 /tmp/openclaw：實測該處存在 stale boot_history（舊世代殘留），
        # 默認回落會回報錯誤 build_sha —— 解析不到即拒讀，fail-close。
        facts["errors"].append("engine_environ_missing_data_dir_refuse_tmp_default")
        return facts
    facts["data_dir"] = data_dir

    boot_history_path = str(Path(data_dir) / "boot_history.jsonl")
    facts["boot_history_path"] = boot_history_path
    raw = client.read_text_file(boot_history_path)
    if raw is None:
        facts["errors"].append("boot_history_unreadable")
        return facts

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        component = record.get("component")
        if component == "openclaw_engine":
            build_sha = str(record.get("build_sha") or "").strip()
            if build_sha and build_sha != "unknown":
                facts["engine_build_sha_raw"] = build_sha
                facts["engine_boot_ts"] = record.get("boot_ts")
                facts["engine_binary_path"] = record.get("binary_path")
        elif component == "control_api":
            repo_head = str(record.get("repo_head") or "").strip()
            if repo_head:
                facts["control_api_repo_head"] = repo_head
    if facts["engine_build_sha_raw"] is None:
        facts["errors"].append("boot_history_has_no_engine_build_sha")
    return facts


# ---------------------------------------------------------------------------
# gap 豁免面判定（import 唯一正本，禁複製豁免表）
# ---------------------------------------------------------------------------


def _classify_gap_rust_touch(
    repo: Path, engine_sha: str, head_sha: str
) -> dict[str, Any]:
    """engine..head gap 是否觸 rust/ 非豁免面。

    豁免面判準 import ``classify_post_approval_path``（``source_generation.py``
    宣告的唯一豁免正本，per-path deny-by-default 分類器）；本檔不出現第二份
    豁免表。判準：任一 changed path 以 ``rust/`` 開頭且 **非豁免** → 需 rebuild。
    import 失敗 → error（呼叫端 fail-close 為 INDETERMINATE）。
    """
    out: dict[str, Any] = {
        "changed_path_count": None,
        "touches_rust_non_exempt": None,
        "rust_paths_sample": [],
        "error": None,
    }
    try:
        research_root = Path(__file__).resolve().parents[1] / "research"
        if str(research_root) not in sys.path:
            sys.path.insert(0, str(research_root))
        from cost_gate_learning_lane.standing_envelope_post_approval_drift_gate import (  # noqa: E501
            classify_post_approval_path,
        )
    except Exception as exc:  # pragma: no cover - import 環境損壞時的 fail-close
        out["error"] = f"exempt_policy_import_failed:{type(exc).__name__}"
        return out

    diff_text = _local_git_text(repo, ["diff", "--name-only", f"{engine_sha}..{head_sha}"])
    if diff_text is None:
        out["error"] = "gap_diff_unavailable"
        return out
    paths = [p for p in diff_text.splitlines() if p.strip()]
    out["changed_path_count"] = len(paths)
    rust_hits: list[str] = []
    for path in paths:
        if not path.startswith("rust/"):
            continue
        item = classify_post_approval_path(path)
        if not item.get("exempt"):
            rust_hits.append(path)
    out["touches_rust_non_exempt"] = bool(rust_hits)
    out["rust_paths_sample"] = rust_hits[:20]
    return out


# ---------------------------------------------------------------------------
# 分類 + packet
# ---------------------------------------------------------------------------


def build_packet(
    local_repo_root: Path,
    *,
    client: RemoteHostClient,
    remote_repo_root: str,
    remote_label: str,
    ls_remote_timeout: int = 20,
) -> dict[str, Any]:
    local_repo_root = local_repo_root.resolve()
    reasons: list[str] = []

    mac_head = _local_git_text(local_repo_root, ["rev-parse", "HEAD"])
    remote_head_info = resolve_true_remote_head(local_repo_root, timeout=ls_remote_timeout)
    true_remote_head = remote_head_info.get("sha")
    linux_head = client.git_text(["rev-parse", "HEAD"])
    linux_origin_main = client.git_text(["rev-parse", "origin/main"])
    engine_facts = resolve_engine_facts(client)
    reasons.extend(engine_facts.get("errors") or [])

    engine_full = None
    if engine_facts.get("engine_build_sha_raw"):
        # boot_history 的 build_sha 可能是短前綴 —— 在 Mac 側展開為 full sha。
        engine_full = _expand_commit(local_repo_root, str(engine_facts["engine_build_sha_raw"]))
        if engine_full is None:
            reasons.append("engine_build_sha_not_resolvable_in_local_repo")

    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "boundary": BOUNDARY,
        "local_repo_root": str(local_repo_root),
        "remote_repo_root": remote_repo_root,
        "remote_label": remote_label,
        "mutated_remote": False,
        "mutated_local": False,
        "heads": {
            "mac_head": mac_head,
            "true_remote_head": true_remote_head,
            "true_remote_head_source": remote_head_info.get("source"),
            "true_remote_head_stale_possible": remote_head_info.get("stale_possible"),
            "linux_head": linux_head,
            "linux_origin_main": linux_origin_main,
            "engine_build_sha_raw": engine_facts.get("engine_build_sha_raw"),
            "engine_build_sha": engine_full,
            "control_api_repo_head": engine_facts.get("control_api_repo_head"),
        },
        "engine": {
            "pid": engine_facts.get("engine_pid"),
            "data_dir": engine_facts.get("data_dir"),
            "boot_history_path": engine_facts.get("boot_history_path"),
            "boot_ts": engine_facts.get("engine_boot_ts"),
            "binary_path": engine_facts.get("engine_binary_path"),
        },
        "gap": None,
    }

    # ── fail-close：四頭任何一頭缺失即 INDETERMINATE，不猜 ──
    if mac_head is None:
        reasons.append("mac_head_unavailable")
    if true_remote_head is None:
        reasons.append("true_remote_head_unavailable")
    if linux_head is None:
        reasons.append("linux_head_unavailable")
    if engine_full is None and "engine_build_sha_not_resolvable_in_local_repo" not in reasons:
        reasons.append("engine_build_sha_unavailable")

    if mac_head is None or true_remote_head is None or linux_head is None or engine_full is None:
        packet["status"] = "INDETERMINATE"
        packet["classification_base"] = "INDETERMINATE"
        packet["reasons"] = reasons
        return packet

    if mac_head == true_remote_head == linux_head == engine_full:
        packet["status"] = "ALL_FOUR_SYNC"
        packet["classification_base"] = "ALL_FOUR_SYNC"
        packet["reasons"] = reasons
        return packet

    if mac_head == true_remote_head == linux_head:
        # 三 git 頭同步，僅 engine 落後 → 驗 ancestor 拓撲後細分。
        anc = _is_ancestor(local_repo_root, engine_full, mac_head)
        if anc is True:
            gap = _classify_gap_rust_touch(local_repo_root, engine_full, mac_head)
            packet["gap"] = gap
            packet["classification_base"] = "GIT_SYNC_ENGINE_ANCESTOR"
            if gap.get("error"):
                reasons.append(str(gap["error"]))
                packet["status"] = "INDETERMINATE"
            elif gap.get("touches_rust_non_exempt"):
                packet["status"] = "HALF_DEPLOY_REBUILD_REQUIRED"
            else:
                packet["status"] = "SOURCE_ONLY_DRIFT"
        else:
            reasons.append("engine_build_sha_not_ancestor_of_git_heads")
            packet["status"] = "INDETERMINATE"
            packet["classification_base"] = "INDETERMINATE"
        packet["reasons"] = reasons
        return packet

    if mac_head != true_remote_head:
        anc = _is_ancestor(local_repo_root, mac_head, true_remote_head)
        if anc is True:
            packet["status"] = "MAC_BEHIND_ORIGIN"
            packet["classification_base"] = "MAC_BEHIND_ORIGIN"
        else:
            reasons.append("mac_head_diverged_or_topology_unresolvable")
            packet["status"] = "INDETERMINATE"
            packet["classification_base"] = "INDETERMINATE"
        if linux_head != true_remote_head:
            reasons.append("linux_head_also_differs_from_true_remote_head")
        packet["reasons"] = reasons
        return packet

    # mac == origin，linux 落後/發散。
    anc = _is_ancestor(local_repo_root, linux_head, true_remote_head)
    if anc is True:
        packet["status"] = "LINUX_BEHIND_ORIGIN"
        packet["classification_base"] = "LINUX_BEHIND_ORIGIN"
    else:
        reasons.append("linux_head_diverged_or_topology_unresolvable")
        packet["status"] = "INDETERMINATE"
        packet["classification_base"] = "INDETERMINATE"
    packet["reasons"] = reasons
    return packet


def _render_human(packet: dict[str, Any]) -> str:
    heads = packet.get("heads") or {}
    lines = [
        f"status: {packet.get('status')}",
        f"classification_base: {packet.get('classification_base')}",
        f"mac_head: {heads.get('mac_head')}",
        (
            f"true_remote_head: {heads.get('true_remote_head')} "
            f"(source={heads.get('true_remote_head_source')}, "
            f"stale_possible={heads.get('true_remote_head_stale_possible')})"
        ),
        f"linux_head: {heads.get('linux_head')}",
        f"engine_build_sha: {heads.get('engine_build_sha')} (raw={heads.get('engine_build_sha_raw')})",
        f"control_api_repo_head: {heads.get('control_api_repo_head')}",
    ]
    gap = packet.get("gap") or {}
    if gap:
        lines.append(
            f"gap: changed={gap.get('changed_path_count')} "
            f"rust_non_exempt={gap.get('touches_rust_non_exempt')} "
            f"sample={gap.get('rust_paths_sample')}"
        )
    lines.append("reasons:")
    for reason in packet.get("reasons") or []:
        lines.append(f"  - {reason}")
    lines.append(f"boundary: {packet.get('boundary')}")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-repo-root", default=".", help="本機 git repo root")
    parser.add_argument("--ssh-host", default="trade-core", help="Linux runtime SSH host")
    parser.add_argument(
        "--remote-repo-root",
        default="/home/ncyu/BybitOpenClaw/srv",
        help="Linux runtime repo root",
    )
    parser.add_argument("--human", action="store_true", help="輸出人讀摘要")
    parser.add_argument("--json-output", type=Path, default=None, help="可選本地 JSON artifact 路徑")
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="status 非 ALL_FOUR_SYNC 時 exit 3",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, client: RemoteHostClient | None = None) -> int:
    args = _parse_args(argv)
    if client is None:
        client = SshHostClient(args.ssh_host, args.remote_repo_root)
        remote_label = f"ssh:{args.ssh_host}"
    else:
        remote_label = f"injected:{type(client).__name__}"

    packet = build_packet(
        Path(args.local_repo_root),
        client=client,
        remote_repo_root=args.remote_repo_root,
        remote_label=remote_label,
    )

    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.human:
        print(_render_human(packet))
    else:
        print(json.dumps(packet, indent=2, sort_keys=True))

    if args.fail_on_drift and packet.get("status") != "ALL_FOUR_SYNC":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
