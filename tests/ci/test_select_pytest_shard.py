from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from helper_scripts.ci.select_pytest_shard import select_nodeids  # noqa: E402


def _nodeids(count: int) -> list[str]:
    return [f"tests/structure/test_governance_{index:04d}.py::test_case" for index in range(count)]


def test_selection_is_permutation_independent_and_digest_bound() -> None:
    nodeids = _nodeids(19)

    forward = select_nodeids(nodeids, shard_index=2, shard_count=5, minimum_count=19)
    reverse = select_nodeids(
        reversed(nodeids), shard_index=2, shard_count=5, minimum_count=19
    )

    assert reverse == forward
    assert forward.full_count == 19
    assert forward.selected_count == 4
    assert forward.full_manifest_sha256.startswith("sha256:")
    assert forward.selected_manifest_sha256.startswith("sha256:")


def test_eight_shards_are_exhaustive_disjoint_and_balanced_at_current_minimum() -> None:
    nodeids = _nodeids(4548)
    selections = [
        select_nodeids(nodeids, shard_index=index, shard_count=8, minimum_count=4548)
        for index in range(8)
    ]
    selected_sets = [set(selection.selected_nodeids) for selection in selections]

    assert [selection.selected_count for selection in selections] == [
        569,
        569,
        569,
        569,
        568,
        568,
        568,
        568,
    ]
    assert set().union(*selected_sets) == set(nodeids)
    for left, right in combinations(selected_sets, 2):
        assert left.isdisjoint(right)
    assert len({selection.full_manifest_sha256 for selection in selections}) == 1


@pytest.mark.parametrize(
    ("nodeids", "shard_index", "shard_count", "minimum_count", "message"),
    [
        ([], 0, 1, 0, "must not be empty"),
        (_nodeids(2), 0, 1, 3, "below minimum"),
        ([*_nodeids(2), _nodeids(2)[0]], 0, 1, 1, "duplicate"),
        (["not-tests/test_x.py::test_x"], 0, 1, 1, "must start with tests/"),
        (["tests/test_x.py"], 0, 1, 1, "must identify a test"),
        (["tests/test_x.py::test_x\nforged"], 0, 1, 1, "control character"),
        (["tests/test_x.py::test_\udcff"], 0, 1, 1, "valid UTF-8"),
        (_nodeids(2), 0, 0, 1, "positive integer"),
        (_nodeids(2), -1, 2, 1, "out of range"),
        (_nodeids(2), 2, 2, 1, "out of range"),
        (_nodeids(1), 1, 2, 1, "selected shard is empty"),
    ],
)
def test_invalid_or_incomplete_inputs_fail_closed(
    nodeids: list[str],
    shard_index: int,
    shard_count: int,
    minimum_count: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        select_nodeids(
            nodeids,
            shard_index=shard_index,
            shard_count=shard_count,
            minimum_count=minimum_count,
        )


@pytest.mark.parametrize("field", ["shard_index", "shard_count", "minimum_count"])
def test_boolean_integer_inputs_fail_closed(field: str) -> None:
    arguments = {
        "shard_index": 0,
        "shard_count": 1,
        "minimum_count": 1,
    }
    arguments[field] = True

    with pytest.raises(ValueError, match="integer"):
        select_nodeids(_nodeids(1), **arguments)


class _PluginManager:
    def get_plugin(self, name: str):
        assert name == "terminalreporter"
        return None


class _Config:
    pluginmanager = _PluginManager()

    def __init__(self, **values: object) -> None:
        self._values = values

    def getoption(self, name: str):
        return self._values[name]


class _Item:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid


def test_collection_writes_exact_deterministic_evidence_before_filtering(tmp_path) -> None:
    from helper_scripts.ci.select_pytest_shard import pytest_collection_modifyitems

    evidence = tmp_path / "governance-pytest-shard-1.json"
    items = [_Item(nodeid) for nodeid in reversed(_nodeids(5))]
    config = _Config(
        governance_shard_index=1,
        governance_shard_count=2,
        governance_shard_minimum=5,
        governance_shard_evidence_path=str(evidence),
        governance_shard_source_sha="a" * 40,
    )

    pytest_collection_modifyitems(config, items)

    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert list(payload) == sorted(payload)
    assert payload == {
        "full_count": 5,
        "full_manifest_sha256": select_nodeids(
            _nodeids(5), shard_index=1, shard_count=2, minimum_count=5
        ).full_manifest_sha256,
        "minimum_count": 5,
        "schema_version": "governance_pytest_shard_evidence_v1",
        "selected_count": 2,
        "selected_manifest_sha256": select_nodeids(
            _nodeids(5), shard_index=1, shard_count=2, minimum_count=5
        ).selected_manifest_sha256,
        "selected_nodeids": [_nodeids(5)[1], _nodeids(5)[3]],
        "shard_count": 2,
        "shard_index": 1,
        "source_sha": "a" * 40,
    }
    assert {item.nodeid for item in items} == set(payload["selected_nodeids"])
    assert evidence.read_bytes().endswith(b"\n")

    with pytest.raises(pytest.UsageError, match="already exists"):
        pytest_collection_modifyitems(config, [_Item(nodeid) for nodeid in _nodeids(5)])


@pytest.mark.parametrize(
    ("path", "source_sha"),
    [("evidence.json", None), (None, "a" * 40), ("evidence.json", "A" * 40)],
)
def test_collection_evidence_options_are_all_or_none_and_sha_bound(
    path: str | None, source_sha: str | None
) -> None:
    from helper_scripts.ci.select_pytest_shard import pytest_collection_modifyitems

    config = _Config(
        governance_shard_index=0,
        governance_shard_count=1,
        governance_shard_minimum=1,
        governance_shard_evidence_path=path,
        governance_shard_source_sha=source_sha,
    )
    with pytest.raises(pytest.UsageError, match="evidence"):
        pytest_collection_modifyitems(config, [_Item(_nodeids(1)[0])])


def test_evidence_options_cannot_run_without_shard_options() -> None:
    from helper_scripts.ci.select_pytest_shard import pytest_collection_modifyitems

    config = _Config(
        governance_shard_index=None,
        governance_shard_count=None,
        governance_shard_minimum=None,
        governance_shard_evidence_path="evidence.json",
        governance_shard_source_sha="a" * 40,
    )
    with pytest.raises(pytest.UsageError, match="shard options"):
        pytest_collection_modifyitems(config, [_Item(_nodeids(1)[0])])
