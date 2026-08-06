"""W5 persisted receipt 綁定 × TODO/PROGRESS 投影的鑑別性回歸(round-6 PM 工單)。

背景(2026-07-28 PM audit):round-5 receipts 已在 `aaee7f1a2` 重新發射並提交為
`456bd0c20`,但 TODO.md 與 PROGRESS.md 的 active-state 仍描述 `c2a7263ce` 世代
(「round-5 未提交」「再發射尚欠」)——artifact 是對的,投影是舊的,而讀投影的人
(operator、下一個 wave 的 intake)拿到的是一份與 artifact 矛盾的現實。本檔把
「artifact 實值 ↔ 文檔投影 ↔ 活 ABI」三方釘成機械等值,任何一側漂移即紅:

- 八件 persisted artifact 必須恰好八件、`source_head` 唯一且等於本檔釘住的
  ``EXPECTED_SOURCE_HEAD``(未來合法 re-emission 須在同一 commit 內同步改本常量
  與兩份文檔的 marker——漂移只能是**蓄意**的,不能是遺忘);
- TODO.md 與 PROGRESS.md 各帶恰好一條 ``W5-RECEIPT-BINDING`` marker,其
  `source_head`/`artifacts` 欄位與 artifact 實值逐項相等;
- 兩份文檔內**每一處** ``source_head = <hex>`` 形式的主張都必須等於 artifact
  實值(歷史敘事寫舊世代一律用「bound to `<sha>`」措辭,不得佔用主張格式——
  這正是 round-6 抓到的那類假話的格式);
- 「round-5 未提交」類的死句不得復活(tombstone);
- TODO gate ② 與 PROGRESS 裁決節列出的 PM-owned obligations 必須與活 ABI 的
  `owner_wave=PM` 集合 set-equal(PM addendum 抓到的 4/6 漏列與 W6 誤計不得再發
  生),且每列帶合法 classification token;
- derivation record 的 `remaining_owned_obligation_count` 與
  `obligation_ledger_digest` 等於活 ABI 的當下重算值(義務清單**不得手抄**,
  一律由 ABI 枚舉)。

誠實邊界:本檔只證「repo 內三方投影一致」,不證任何 runtime/效果,也不證
carrier commit 的祖先關係(shallow clone 下 git 拓撲不可用;carrier 只驗格式與
「與 source_head 相異」——emitter 對髒 owned scope 硬拒,artifact 永遠落在綁定
head 之後的另一個 commit)。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_w5_emit as w5_emit  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

# Tier 1 durability anchor 分支四輪複核後的 head(651bd4e38)——八件 persisted
# artifact 當前綁定的 source_head(round 11;round 10 因 evidence 文字本身踩到
# file-line-policy 掃描而被同分支取代)。round 9 綁 f30ede361,
# 而 `209793b70` 之後改了三條 W5-owned path 卻零 re-emission,故本輪一併償還。
# 合法 re-emission 時本常量與兩份文檔的 marker 必須在同一 commit 內一起更新。
EXPECTED_SOURCE_HEAD = "651bd4e38cef0e39545f6f8f378829800feea17f"

RECEIPT_DIR = ROOT / "docs/execution_plan/ai_ml_landing/receipts/S2.4-WP4-W5"
TODO_PATH = ROOT / "TODO.md"
PROGRESS_PATH = ROOT / "docs/execution_plan/ai_ml_landing/PROGRESS.md"
DERIVATION_RECORD = RECEIPT_DIR / "S2.4-WP4-W5-derivation-record.json"

_MARKER_RE = re.compile(
    r"W5-RECEIPT-BINDING: source_head=([0-9a-f]{40}) "
    r"carrier_commit=([0-9a-f]{40}) artifacts=(\d+) round=(\d+) status=([A-Z_]+)"
)
# 主張格式:歷史敘事禁止佔用(舊世代一律寫「bound to `<sha>`」),
# 所以每一個命中都是「現行綁定」的主張,必須等於 artifact 實值。
# E2 round-6 P2-2:全形等號「＝」納入,關掉蓄意規避之外最廉價的變體。
_CLAIM_RE = re.compile(r"source_head\s*[=＝]\s*`?([0-9a-f]{7,40})")
# 現行 receipt 世代的 round 序號;re-emission 時與 EXPECTED_SOURCE_HEAD 同 commit 更新。
EXPECTED_ROUND = 11
_ALLOWED_CLASSIFICATIONS = {
    "source_closure_blocker",
    "accepted_carry_forward",
    "separately_scheduled",
}
# round-6 P1 的死句(regex;原句夾帶 ** 強調,字面量會漏)。引述它們時不得逐字複現
# (描述請改寫,例如「round-5 未提交」)。
_TOMBSTONES = (
    r"未提交\**的第五輪",
    r"第五輪 remediation（未提交",
    r"remediation 已完成但\**未提交",
)


def _artifact_paths() -> list[Path]:
    return sorted(RECEIPT_DIR.glob("*.json"))


def _unique_artifact_source_head() -> str:
    heads = set()
    for path in _artifact_paths():
        payload = json.loads(path.read_text(encoding="utf-8"))
        head = payload.get("source_head")
        assert isinstance(head, str) and re.fullmatch(r"[0-9a-f]{40}", head), path.name
        heads.add(head)
    assert len(heads) == 1, {"non_unique_source_heads": sorted(heads)}
    return heads.pop()


def test_eight_artifacts_bind_exactly_one_expected_source_head() -> None:
    paths = _artifact_paths()
    assert len(paths) == 8, [p.name for p in paths]
    head = _unique_artifact_source_head()
    assert head == EXPECTED_SOURCE_HEAD, {
        "artifact_source_head": head,
        "expected_source_head": EXPECTED_SOURCE_HEAD,
        "hint": "合法 re-emission 須同 commit 更新本常量與 TODO/PROGRESS 的 marker",
    }


def test_receipt_binding_markers_agree_with_the_artifacts() -> None:
    head = _unique_artifact_source_head()
    count = len(_artifact_paths())
    for path in (TODO_PATH, PROGRESS_PATH):
        text = path.read_text(encoding="utf-8")
        markers = _MARKER_RE.findall(text)
        assert len(markers) == 1, {
            "path": str(path.relative_to(ROOT)),
            "marker_count": len(markers),
        }
        marker_head, carrier, artifacts, round_no, status = markers[0]
        assert marker_head == head, {
            "path": str(path.relative_to(ROOT)),
            "marker_source_head": marker_head,
            "artifact_source_head": head,
        }
        assert int(artifacts) == count, (path.name, artifacts, count)
        assert int(round_no) == EXPECTED_ROUND, (path.name, round_no)
        assert status == "COMMITTED", (path.name, status)
        # emitter 對髒 owned scope 硬拒 ⇒ artifact 永遠由綁定 head 之後的另一個
        # commit 承載;carrier==source_head 只可能出自手寫投影。
        assert carrier != marker_head, path.name


def test_every_source_head_claim_in_the_docs_matches_the_artifacts() -> None:
    head = _unique_artifact_source_head()
    for path in (TODO_PATH, PROGRESS_PATH):
        text = path.read_text(encoding="utf-8")
        for claim in _CLAIM_RE.findall(text):
            assert head.startswith(claim), {
                "path": str(path.relative_to(ROOT)),
                "stale_claim": claim,
                "artifact_source_head": head,
                "hint": "歷史世代請寫「bound to `<sha>`」,主張格式只給現行綁定",
            }


def test_stale_uncommitted_round5_claims_stay_dead() -> None:
    for path in (TODO_PATH, PROGRESS_PATH):
        text = path.read_text(encoding="utf-8")
        for pattern in _TOMBSTONES:
            assert not re.search(pattern, text), {
                "path": str(path.relative_to(ROOT)),
                "resurrected_phrase": pattern,
            }


def _abi_pm_owned_ids() -> set[str]:
    return {
        row["obligation_id"]
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
        if row["owner_wave"] == "PM"
    }


def test_pm_owned_projection_is_set_equal_to_the_live_abi() -> None:
    abi_ids = _abi_pm_owned_ids()
    assert abi_ids, "live ABI has no PM-owned rows; the projection contract is moot"

    # PROGRESS 裁決節:每列「- `ID` → classification=<token>」。
    progress = PROGRESS_PATH.read_text(encoding="utf-8")
    block_match = re.search(
        r"<!-- W5-PM-OWNED-ADJUDICATION-BEGIN[^>]*-->(.*?)"
        r"<!-- W5-PM-OWNED-ADJUDICATION-END -->",
        progress,
        re.DOTALL,
    )
    assert block_match, "PROGRESS.md is missing the PM adjudication block markers"
    rows = re.findall(
        r"^- `([A-Z0-9_]+)` → classification=([a-z_]+)",
        block_match.group(1),
        re.MULTILINE,
    )
    progress_ids = {obligation_id for obligation_id, _ in rows}
    # E2 round-6 P2-1:set-equality 容忍重複列——merge-conflict 式的「同 id 兩列、
    # classification 互相矛盾」曾實測為綠;列數必須等於去重後的 id 數。
    assert len(rows) == len(progress_ids), {
        "duplicated_ids": sorted(
            obligation_id
            for obligation_id in progress_ids
            if sum(1 for row_id, _ in rows if row_id == obligation_id) > 1
        ),
    }
    assert progress_ids == abi_ids, {
        "missing_from_progress": sorted(abi_ids - progress_ids),
        "not_pm_owned_in_the_live_abi": sorted(progress_ids - abi_ids),
    }
    for obligation_id, classification in rows:
        assert classification in _ALLOWED_CLASSIFICATIONS, (
            obligation_id,
            classification,
        )

    # TODO gate ②:marker 區間內的 backtick id 集合同樣 set-equal。
    todo = TODO_PATH.read_text(encoding="utf-8")
    todo_match = re.search(
        r"<!-- W5-PM-ADJ-IDS-BEGIN -->(.*?)<!-- W5-PM-ADJ-IDS-END -->",
        todo,
        re.DOTALL,
    )
    assert todo_match, "TODO.md is missing the PM adjudication id markers"
    todo_ids = set(re.findall(r"`([A-Z0-9_]+)`", todo_match.group(1)))
    assert todo_ids == abi_ids, {
        "missing_from_todo": sorted(abi_ids - todo_ids),
        "not_pm_owned_in_the_live_abi": sorted(todo_ids - abi_ids),
    }


def test_derivation_record_ledger_matches_the_live_abi() -> None:
    record = json.loads(DERIVATION_RECORD.read_text(encoding="utf-8"))
    live_ledger = w5_emit.w5_remaining_obligation_ledger()
    assert record["remaining_owned_obligation_count"] == len(live_ledger)
    assert record["obligation_ledger_digest"] == validator.canonical_digest(
        live_ledger
    ), "persisted obligation ledger drifted from the live ABI"
