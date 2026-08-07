"""Regression: 綁定 committed 的 LW1 operator action packet 與它的 generator。

2026-08-02 的 Tier 1 改動換掉了 generator 的前置集合,但 committed artifact 沒有
跟著重生,而 CI 全綠——因為沒有任何測試引用該 artifact。operator 照 stale packet
provision 會採購已被移除的外部服務。本檔把 artifact 釘回 generator:
①它自己的 validator 必須無錯 ②source_binding 與 pin 自洽
③用 generator 以相同輸入重建必須與 committed 內容 canonical 等值。

不得依賴 wall-clock 或硬編日期:所有時間資料一律取自 committed inventory。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2e_lw1_action_packet as action  # noqa: E402

REPORTS = ROOT / "docs" / "CCAgentWorkSpace" / "PM" / "workspace" / "reports"
COMMITTED_PACKET_PATH = (
    REPORTS / "2026-08-02--s2e_lw1_external_prerequisite_action_packet.json"
)
COMMITTED_INVENTORY_PATH = REPORTS / "2026-08-02--s2e_lw1_readonly_inventory.json"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2)


@pytest.fixture(scope="module")
def committed_packet() -> dict:
    return _load(COMMITTED_PACKET_PATH)


@pytest.fixture(scope="module")
def committed_inventory() -> dict:
    return _load(COMMITTED_INVENTORY_PATH)


def test_committed_action_packet_passes_its_own_validator(
    committed_packet: dict,
) -> None:
    """committed artifact 用 generator 自己的 validator 必須零錯。"""

    errors = action.validate_s2e_lw1_operator_action_packet(
        committed_packet, repo_root=ROOT
    )
    assert errors == [], (
        "committed LW1 action packet 已與 generator 漂移;operator 會照 stale "
        f"packet 做事。errors={errors}"
    )


def test_committed_action_packet_source_binding_is_self_consistent(
    committed_packet: dict,
) -> None:
    """pin 的 commit 必須在本 branch 可達,且 tree 與該 commit 相符。"""

    binding = committed_packet["source_binding"]
    head = binding["implementation_checkpoint_head"]
    assert binding["worktree_clean_at_build"] is True

    resolved = _git(ROOT, "rev-parse", f"{head}^{{commit}}")
    assert resolved == head, (
        f"implementation_checkpoint_head {head} 無法解析為 commit(得 {resolved})"
    )
    merge_base = _git(ROOT, "merge-base", "HEAD", head)
    assert merge_base == head, (
        f"implementation_checkpoint_head {head} 不是目前 HEAD 的祖先"
    )
    assert _git(ROOT, "rev-parse", f"{head}^{{tree}}") == (
        binding["implementation_checkpoint_tree"]
    ), "implementation_checkpoint_tree 與 pin 的 commit tree 不符"


def test_committed_action_packet_is_regenerable_by_its_generator(
    committed_packet: dict,
    committed_inventory: dict,
    tmp_path: Path,
) -> None:
    """用 generator 以相同輸入重建,結果必須與 committed 內容 canonical 等值。

    generator 要求 clean checkpoint 並綁「當下 HEAD」,而開發工作樹可能是髒的、
    HEAD 也已前進。因此在 tmp 目錄做一份 local clone 並 detach 到 packet 自己
    pin 的 checkpoint:該 clone 必然 clean,且 HEAD 正是 pin 的 commit,重建的
    source_binding 才是真正的同輸入比對,而不是放寬 generator 的 clean-tree 要求。
    """

    head = committed_packet["source_binding"]["implementation_checkpoint_head"]
    clone = tmp_path / "checkpoint_clone"
    _git(ROOT, "clone", "--quiet", "--local", "--no-checkout", str(ROOT), str(clone))
    _git(clone, "checkout", "--quiet", "--detach", head)
    assert _git(clone, "status", "--porcelain=v1") == ""
    assert _git(clone, "rev-parse", "HEAD") == head

    rebuilt = action.build_s2e_lw1_operator_action_packet(
        repo_root=clone,
        inventory=committed_inventory,
    )

    assert rebuilt["packet_digest"] == committed_packet["packet_digest"], (
        "重建 packet 的 digest 與 committed 不符:artifact 與 generator 已漂移"
    )
    assert _canonical(rebuilt) == _canonical(committed_packet), (
        "重建 packet 與 committed 內容不是 canonical 等值"
    )
