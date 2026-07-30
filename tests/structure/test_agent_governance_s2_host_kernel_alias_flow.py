"""Adversarial alias/control-flow deltas for the S2 host-kernel AST scanner."""

from __future__ import annotations

from test_agent_governance_s2_host_kernel import _raw_command_findings


def _scan_twice(tmp_path, name: str, source: str) -> list[str]:
    path = tmp_path / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    first = _raw_command_findings(path, exec_family=False)
    assert _raw_command_findings(path, exec_family=False) == first
    return first


def test_direct_alias_mutation_flows_back_to_the_original_receiver(tmp_path):
    findings = _scan_twice(
        tmp_path,
        "direct_alias",
        "def f(key, expr):\n"
        "    source = [{}, __builtins__]\n"
        "    outer = []\n"
        "    alias = outer\n"
        "    alias.extend(source)\n"
        "    return outer[1][key](expr)\n",
    )
    assert any("dynamic execution subscript" in item for item in findings), findings


def test_nested_and_chained_alias_mutations_flow_bidirectionally(tmp_path):
    cases = {
        "nested_alias": (
            "    outer = {'slot': []}\n"
            "    alias = outer['slot']\n"
            "    alias.extend(source)\n"
            "    return outer['slot'][1][key](expr)\n"
        ),
        "chained_alias": (
            "    outer = []\n"
            "    first = outer\n"
            "    second = first\n"
            "    second.extend(source)\n"
            "    return outer[1][key](expr)\n"
        ),
    }
    for name, body in cases.items():
        findings = _scan_twice(
            tmp_path,
            name,
            "def f(key, expr):\n    source = [{}, __builtins__]\n" + body,
        )
        assert any("dynamic execution subscript" in item for item in findings), findings


def test_control_flow_mutations_taint_each_possible_sequence_position(tmp_path):
    blocks = {
        "if": "    if flag:\n        outer.append({})\n",
        "loop": "    for _ in values:\n        outer.append({})\n",
        "try": (
            "    try:\n        risky()\n        outer.append({})\n"
            "    except Exception:\n        pass\n"
        ),
    }
    for name, block in blocks.items():
        for index in (0, 1):
            findings = _scan_twice(
                tmp_path,
                f"{name}_{index}",
                "def f(flag, values, key, expr):\n"
                "    outer = []\n"
                f"{block}"
                "    outer.append(__builtins__)\n"
                f"    return outer[{index}][key](expr)\n",
            )
            assert any("dynamic execution subscript" in item for item in findings), (
                name,
                index,
                findings,
            )


def test_dynamic_alias_and_uncertain_index_fail_closed(tmp_path):
    sources = (
        "def f(slot, key, expr):\n"
        "    outer = {'safe': []}\n    alias = outer[slot]\n"
        "    alias.append(__builtins__)\n    return outer['safe'][0][key](expr)\n",
        "def f(flag, index, key, expr):\n"
        "    outer = []\n    if flag:\n        outer.append({})\n"
        "    outer.append(__builtins__)\n    return outer[index][key](expr)\n",
    )
    for index, source in enumerate(sources):
        findings = _scan_twice(tmp_path, f"dynamic_{index}", source)
        assert any("dynamic execution subscript" in item for item in findings), findings


def test_known_prefixes_and_metadata_keys_stay_precise(tmp_path):
    cases = {
        "direct_prefix": (
            "    outer = [{}]\n    alias = outer\n"
            "    if flag:\n        alias.append(__builtins__)\n"
            "    return outer[0][key](expr)\n"
        ),
        "nested_prefix": (
            "    outer = {'slot': [{}]}\n    alias = outer['slot']\n"
            "    if flag:\n        alias.append(__builtins__)\n"
            "    return outer['slot'][0][key](expr)\n"
        ),
        "metadata": (
            "    outer = {'sequence_length': {}, 'sequence_uncertain': {}, 'slot': []}\n"
            "    alias = outer['slot']\n    if flag:\n        alias.append(__builtins__)\n"
            "    return outer['sequence_length'][key](expr)\n"
        ),
    }
    for name, body in cases.items():
        assert _scan_twice(tmp_path, name, "def f(flag, key, expr):\n" + body) == []
