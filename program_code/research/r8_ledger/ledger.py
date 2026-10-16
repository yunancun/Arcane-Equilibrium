"""只追加的研究帳與預登記約束；鏈頭須另提交到倉庫作外部錨點。"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re

GENESIS = "0" * 64
DEFAULT_EMBARGO_SECONDS = 7 * 86400
LEDGERS = ("preregistrations", "trials", "holdouts")
DEFAULT_BOUNDARIES = (
    "2022-01-01T00:00:00Z", "2025-07-01T00:00:00Z",
    "2026-01-01T00:00:00Z", "2026-05-15T00:00:00Z", "2026-10-01T00:00:00Z",
)


class LedgerError(ValueError):
    """登記、身份、鏈或區間不符合契約。"""


class HoldoutDenied(LedgerError):
    """拒絕時不附帶任何授權區間。"""


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LedgerError("資料必須是有限數值的標準化 JSON") from exc


def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise LedgerError("須提供小寫 SHA-256")
    return value


def _required(record, fields):
    if not isinstance(record, dict):
        raise LedgerError("紀錄須為物件")
    for field in fields:
        if field not in record or record[field] is None or record[field] == "" or record[field] == {} or record[field] == []:
            raise LedgerError("缺必填欄位: " + field)
    canonical(record)


def _number(value, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LedgerError("須為有限數值")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise LedgerError("數值超出範圍")
    return value


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise LedgerError("須為整數且不低於下限")
    return value


def _time(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
            raise ValueError("需要 UTC 時區")
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise LedgerError("時間須為含時區的 UTC ISO8601") from exc


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _range(value):
    _required(value, ("start", "end"))
    start, end = _time(value["start"]), _time(value["end"])
    if start >= end:
        raise LedgerError("區間須為遞增且非空的半開區間")
    return start, end


def split_intervals(boundaries=DEFAULT_BOUNDARIES, *, generations=(1, 2),
                    label_period_seconds=0, max_holding_seconds=0,
                    embargo_seconds=DEFAULT_EMBARGO_SECONDS):
    """空窗一律從後一段開頭扣除；回看資料由未來資料載入器另行限制。"""
    if len(boundaries) != len(generations) + 3 or not generations:
        raise LedgerError("切分日期與 holdout 世代數不符")
    if len(set(generations)) != len(generations) or list(generations) != sorted(generations):
        raise LedgerError("每代只能綁一段 holdout")
    for generation in generations:
        _integer(generation, 1)
    gap = max(DEFAULT_EMBARGO_SECONDS, _number(label_period_seconds, 0),
              _number(max_holding_seconds, 0), _number(embargo_seconds, 0))
    dates = [_time(x) for x in boundaries]
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise LedgerError("切分重疊或順序錯誤")
    result = []
    for i, (start, end) in enumerate(zip(dates, dates[1:])):
        if i:
            start += timedelta(seconds=gap)
        if start >= end:
            raise LedgerError("扣除空窗後沒有可用資料")
        result.append({"id": ("train", "validation")[i] if i < 2 else "holdout-" + str(generations[i-2]),
                       "kind": ("train", "validation")[i] if i < 2 else "holdout",
                       "generation": None if i < 2 else generations[i-2],
                       "start": _iso(start), "end": _iso(end)})
    return result


def _splits(record):
    segments = record["time_splits"]
    if not isinstance(segments, list) or len(segments) < 3:
        raise LedgerError("至少需要訓練、驗證與一段 holdout")
    data_start, data_end = _range(record["data_range"])
    previous = None
    ids, generations = set(), set()
    gap = max(DEFAULT_EMBARGO_SECONDS, record["label_period_seconds"], record["max_holding_seconds"])
    checked = []
    for i, segment in enumerate(segments):
        _required(segment, ("id", "kind", "start", "end"))
        expected = ("train", "validation")[i] if i < 2 else "holdout"
        if segment["kind"] != expected or segment["id"] in ids:
            raise LedgerError("切分種類、順序或代號錯誤")
        ids.add(segment["id"])
        start, end = _range(segment)
        if start < data_start or end > data_end or previous is not None and start < previous:
            raise LedgerError("區間重疊、倒序或超出資料範圍")
        if previous is not None:
            start = max(start, previous + timedelta(seconds=gap))
        if start >= end:
            raise LedgerError("扣除空窗後沒有可用資料")
        if i >= 2:
            generation = _integer(segment.get("generation"), 1)
            if generation in generations or generations and generation <= max(generations):
                raise LedgerError("holdout 世代重複或倒序")
            generations.add(generation)
        checked.append({**segment, "start": _iso(start), "end": _iso(end)})
        previous = end
    return checked


def _prereg(record):
    fields = ("hypothesis_id", "family", "economic_mechanism", "decision_period", "expected_holding_seconds",
              "expected_turnover", "pessimistic_cost_ratio", "data_range", "time_splits", "primary_metric",
              "candidate_thresholds", "multiple_testing", "max_lookback_seconds", "label_period_seconds",
              "max_holding_seconds", "selection", "split_rationale", "power_estimate")
    _required(record, fields)
    period = record["decision_period"]
    _required(period, ("unit", "value"))
    if period["unit"] not in ("second", "minute", "hour", "day") or _number(period["value"], 0) == 0:
        raise LedgerError("決策週期不合法")
    if period["unit"] in ("second", "minute"):
        _required(record, ("non_speed_edge",))
    for key in ("expected_holding_seconds", "expected_turnover", "pessimistic_cost_ratio", "max_lookback_seconds", "label_period_seconds", "max_holding_seconds"):
        _number(record[key], 0)
    selection = record["selection"]
    _required(selection, ("type", "rule"))
    if selection["type"] == "time_series":
        _required(selection, ("known_at_period_start",))
        if _time(selection["known_at_period_start"]) > _range(record["data_range"])[0]:
            raise LedgerError("選取規則須在期間起點可知")
    elif selection["type"] in ("cross_sectional", "filtered"):
        if not selection.get("point_in_time_universe_source") and not selection.get("no_delistings_proof"):
            raise LedgerError("缺含下架品種的時點清單或無下架證明")
    else:
        raise LedgerError("不支援的選取類型")
    if "previous_no_go" not in record:
        raise LedgerError("須顯式交代 previous_no_go；首次登記填 null")
    if record["previous_no_go"] is not None:
        _required(record["previous_no_go"], ("decision_ref", "differences"))
    multiple = record["multiple_testing"]
    _required(multiple, ("method", "fdr", "members", "members_sha256"))
    members = multiple["members"]
    if multiple["method"] != "BH" or not isinstance(members, list) or not all(isinstance(x, str) and x for x in members):
        raise LedgerError("多重檢驗須為 BH 與非空假說集合")
    if len(set(members)) != len(members) or record["hypothesis_id"] not in members:
        raise LedgerError("家族成員重複或未含本假說")
    if sha256(sorted(members)) != _hash(multiple["members_sha256"]):
        raise LedgerError("家族成員雜湊不符")
    if not 0 < _number(multiple["fdr"], 0, 1) < 1:
        raise LedgerError("FDR 須介於 0 與 1")
    return {**record, "time_splits": _splits(record)}


class ResearchLedger:
    """在呼叫者指定的目錄寫帳；所有公開動作在同一把檔案鎖內完成。"""

    def __init__(self, out):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self):
        with (self.out / ".ledger.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self, name, pinned=None):
        path = self.out / (name + ".jsonl")
        raw = path.read_bytes() if path.exists() else b""
        if raw and not raw.endswith(b"\n"):
            raise LedgerError("帳本末筆不完整")
        previous, records = GENESIS, []
        seen = {GENESIS}
        for index, line in enumerate(raw.splitlines(), 1):
            try:
                row = json.loads(line)
                if set(row) != {"sequence", "previous", "payload", "hash"}:
                    raise ValueError("結構錯誤")
                unsigned = {k: row[k] for k in ("sequence", "previous", "payload")}
                if row["sequence"] != index or row["previous"] != previous or row["hash"] != sha256(unsigned):
                    raise ValueError("鏈不完整")
                if canonical(row) != line:
                    raise ValueError("不是標準化 JSON")
            except (ValueError, TypeError, KeyError) as exc:
                raise LedgerError(name + " 鏈被改寫或損壞") from exc
            previous = row["hash"]
            seen.add(previous)
            records.append(row)
        if pinned is not None and _hash(pinned) not in seen:
            raise LedgerError(name + " 找不到已提交的鏈頭")
        return records

    def _append(self, name, payload):
        rows = self._read(name)
        row = {"sequence": len(rows) + 1, "previous": rows[-1]["hash"] if rows else GENESIS, "payload": payload}
        row["hash"] = sha256(row)
        # 單一 writer、單筆寫入並 fsync；崩潰殘留的半筆在讀取時明確拒絕。
        import os
        with (self.out / (name + ".jsonl")).open("ab") as stream:
            stream.write(canonical(row) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return row["hash"]

    def verify_heads(self, pinned):
        if not isinstance(pinned, dict) or set(pinned) != set(LEDGERS):
            raise LedgerError("須提供三本帳的已提交鏈頭")
        with self._lock():
            return {name: self._head(self._read(name, pinned[name])) for name in LEDGERS}

    @staticmethod
    def _head(rows):
        return rows[-1]["hash"] if rows else GENESIS

    def export_heads(self):
        with self._lock():
            return {name: self._head(self._read(name)) for name in LEDGERS}

    def _registration(self, hypothesis_id):
        matches = [r["payload"] for r in self._read("preregistrations") if r["payload"]["record"]["hypothesis_id"] == hypothesis_id]
        if len(matches) != 1:
            raise LedgerError("假說必須先唯一預登記")
        return matches[0]

    def preregister(self, record, registered_at):
        record = _prereg(json.loads(canonical(record)))
        at = _time(registered_at)
        with self._lock():
            for row in self._read("preregistrations"):
                old = row["payload"]["record"]
                if old["hypothesis_id"] == record["hypothesis_id"]:
                    raise LedgerError("假說代號已登記；修訂須另給代號並保留譜系")
                if old["family"] == record["family"] and old["multiple_testing"] != record["multiple_testing"]:
                    raise LedgerError("同一家族的 BH 綁定不一致")
            digest = sha256(record)
            self._append("preregistrations", {"record": record, "record_sha256": digest, "registered_at": _iso(at)})
            return digest

    def record_trial(self, record):
        fields = ("trial_id", "hypothesis_id", "generation", "variant_parameters", "data_window", "manifest_sha256", "data_files",
                  "code_commit", "cost_model", "fill_model", "configuration", "configuration_sha256", "engine", "dependencies", "time_semantics",
                  "status", "result_summary", "started_at", "ended_at", "sharpe", "sharpe_frequency", "return_count", "skewness", "excess_kurtosis", "returns_sha256", "p_value")
        # 空變體與無外部相依是合法值，但鍵必須存在。
        statistics = ("sharpe", "return_count", "skewness", "excess_kurtosis", "returns_sha256")
        unavailable = record.get("status") in ("failed", "aborted") and any(record.get(k) is None for k in statistics)
        allowed_empty = ("variant_parameters", "dependencies") + (statistics if unavailable else ())
        _required(record, tuple(x for x in fields if x not in allowed_empty))
        if unavailable:
            if any(k not in record for k in statistics):
                raise LedgerError("缺 DSR 輸入欄位")
            _required(record, ("statistics_unavailable_reason",))
        for key in ("parent_trial_id", "random_seed", "variant_parameters", "dependencies"):
            if key not in record:
                raise LedgerError("缺實驗身份: " + key)
        if not isinstance(record["variant_parameters"], dict) or not isinstance(record["dependencies"], dict):
            raise LedgerError("變體參數與相依版本須為物件")
        _integer(record["generation"], 1)
        for key in ("manifest_sha256", "configuration_sha256"):
            _hash(record[key])
        if not isinstance(record["data_files"], dict) or not record["data_files"]:
            raise LedgerError("缺資料檔雜湊")
        for value in record["data_files"].values():
            _hash(value)
        if not isinstance(record["code_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", record["code_commit"]):
            raise LedgerError("須有完整程式 commit")
        for key in ("cost_model", "fill_model", "engine"):
            _required(record[key], ("id", "version"))
        _required(record["configuration"], ("strategy_parameters", "cost_model_parameters"))
        if sha256(record["configuration"]) != record["configuration_sha256"]:
            raise LedgerError("設定雜湊不符")
        _required(record["time_semantics"], ("known_at", "fill_at", "simulated_latency_ms"))
        _number(record["time_semantics"]["simulated_latency_ms"], 0)
        for key in ("sharpe", "skewness", "excess_kurtosis"):
            if record[key] is not None or not unavailable:
                _number(record[key])
        if record["returns_sha256"] is not None or not unavailable:
            _hash(record["returns_sha256"])
        _required(record["sharpe_frequency"], ("unit", "seconds", "annualized"))
        if record["sharpe_frequency"]["annualized"] is not False or _number(record["sharpe_frequency"]["seconds"], 0) == 0:
            raise LedgerError("Sharpe 必須是不年化且與報酬筆數同頻的每期值")
        if record["return_count"] is not None or not unavailable:
            _integer(record["return_count"], 0 if unavailable else 2)
        _number(record["p_value"], 0, 1)
        if record["random_seed"] is not None:
            _integer(record["random_seed"])
        if record["status"] not in ("completed", "failed", "aborted"):
            raise LedgerError("試驗狀態不合法")
        start, end = _time(record["started_at"]), _time(record["ended_at"])
        if end < start:
            raise LedgerError("試驗結束早於開始")
        ds, de = _range(record["data_window"])
        with self._lock():
            reg = self._registration(record["hypothesis_id"])
            if start <= _time(reg["registered_at"]):
                raise LedgerError("試驗必須嚴格晚於預登記")
            rs, re_ = _range(reg["record"]["data_range"])
            if ds < rs or de > re_:
                raise LedgerError("試驗資料窗超出預登記範圍")
            trials = [row["payload"] for row in self._read("trials")]
            if any(t["trial_id"] == record["trial_id"] for t in trials):
                raise LedgerError("試驗代號重複")
            parent = record["parent_trial_id"]
            if record["generation"] > 1 and parent is None:
                raise LedgerError("後代試驗必須引用親代")
            if parent is not None and not any(t["trial_id"] == parent and t["generation"] < record["generation"] and t["family"] == reg["record"]["family"] for t in trials):
                raise LedgerError("親代不存在或世代順序錯誤")
            return self._append("trials", {**record, "family": reg["record"]["family"], "preregistration_sha256": reg["record_sha256"]})

    def _segment(self, hypothesis_id, segment_id):
        reg = self._registration(hypothesis_id)
        matches = [s for s in reg["record"]["time_splits"] if s["kind"] == "holdout" and s["id"] == segment_id]
        if len(matches) != 1:
            raise HoldoutDenied("不存在該 holdout 段")
        return matches[0]

    def seal_holdout(self, hypothesis_id, segment_id):
        with self._lock():
            segment = self._segment(hypothesis_id, segment_id)
            events = [r["payload"] for r in self._read("holdouts")]
            identity = {k: segment[k] for k in ("start", "end")}
            if any(e.get("interval") == identity and e["action"] == "sealed" for e in events):
                raise HoldoutDenied("該資料段已封存")
            return self._append("holdouts", {"action": "sealed", "hypothesis_id": hypothesis_id, "segment_id": segment_id,
                                           "generation": segment["generation"], "interval": identity, "at": _iso(datetime.now(timezone.utc))})

    def open_holdout(self, hypothesis_id, segment_id, generation, candidates_sha256):
        _hash(candidates_sha256)
        _integer(generation, 1)
        with self._lock():
            segment = self._segment(hypothesis_id, segment_id)
            events = [r["payload"] for r in self._read("holdouts")]
            identity = {k: segment[k] for k in ("start", "end")}
            reason = None
            if generation != segment["generation"]:
                reason = "世代與登記不符"
            elif not any(e["action"] == "sealed" and e.get("interval") == identity and e["generation"] == generation for e in events):
                reason = "資料段尚未封存"
            # 不同假說改名或部分重疊都不能重新開啟已看過的時段。
            elif any(e["action"] == "opened" and _range(e["interval"])[0] < _range(identity)[1] and _range(identity)[0] < _range(e["interval"])[1] for e in events):
                reason = "此 holdout 已開啟，禁止再次讀取"
            event = {"action": "denied" if reason else "opened", "hypothesis_id": hypothesis_id,
                     "segment_id": segment_id, "generation": generation, "candidates_sha256": candidates_sha256,
                     "at": _iso(datetime.now(timezone.utc))}
            if reason:
                self._append("holdouts", {**event, "reason": reason})
                raise HoldoutDenied(reason)
            self._append("holdouts", {**event, "interval": identity})
            return dict(identity)

    def family_trial_count(self, family):
        with self._lock():
            return sum(r["payload"]["family"] == family for r in self._read("trials"))

    def dsr_inputs(self, family):
        keys = ("trial_id", "sharpe", "sharpe_frequency", "return_count", "skewness", "excess_kurtosis", "returns_sha256", "status")
        with self._lock():
            trials = [r["payload"] for r in self._read("trials") if r["payload"]["family"] == family]
            return {"trial_count": len(trials), "trials": [{**{k: t[k] for k in keys}, "statistics_unavailable_reason": t.get("statistics_unavailable_reason")} for t in trials]}

    def benjamini_hochberg(self, hypothesis_id, p_values, members_sha256, fdr):
        with self._lock():
            binding = self._registration(hypothesis_id)["record"]["multiple_testing"]
        if not isinstance(p_values, dict) or sorted(p_values) != sorted(binding["members"]):
            raise LedgerError("BH 必須包含完整且相同的預登記家族")
        if _hash(members_sha256) != binding["members_sha256"] or sha256(sorted(p_values)) != members_sha256 or fdr != binding["fdr"]:
            raise LedgerError("BH 家族或固定 FDR 水準不符")
        for p in p_values.values():
            _number(p, 0, 1)
        ordered = sorted(p_values, key=lambda key: (p_values[key], key))
        count, running, adjusted = len(ordered), 1.0, {}
        for rank in range(count, 0, -1):
            key = ordered[rank-1]
            running = min(running, p_values[key] * count / rank)
            adjusted[key] = running
        return {key: {"p_value": p_values[key], "adjusted_p": adjusted[key], "rejected": adjusted[key] <= fdr} for key in ordered}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("action", choices=("heads", "verify", "preregister", "trial", "seal", "open"))
    parser.add_argument("--record", help="輸入 JSON 檔；verify 使用三本帳的已提交鏈頭")
    args = parser.parse_args(argv)
    ledger = ResearchLedger(args.out)
    if args.action == "heads":
        result = ledger.export_heads()
    else:
        if not args.record:
            parser.error("此動作需要 --record")
        value = json.loads(Path(args.record).read_text())
        if args.action == "verify":
            result = ledger.verify_heads(value)
        elif args.action == "preregister":
            result = ledger.preregister(value["record"], value["registered_at"])
        elif args.action == "trial":
            result = ledger.record_trial(value)
        elif args.action == "seal":
            result = ledger.seal_holdout(**value)
        else:
            result = ledger.open_holdout(**value)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
