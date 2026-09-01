from __future__ import annotations

from itertools import combinations

import pytest

from helper_scripts.ci.select_pytest_shard import select_nodeids


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
    nodeids = _nodeids(4621)
    selections = [
        select_nodeids(nodeids, shard_index=index, shard_count=8, minimum_count=4621)
        for index in range(8)
    ]
    selected_sets = [set(selection.selected_nodeids) for selection in selections]

    assert [selection.selected_count for selection in selections] == [
        578,
        578,
        578,
        578,
        578,
        577,
        577,
        577,
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
