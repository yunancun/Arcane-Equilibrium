"""只追加研究帳；canonical 以 Python 實作為準，鏈頭及 ledger_id 須另提交作錨點。

filled_periods 與 exposure_matched 的產生方式須由研究工具證明，本帳本無法核實。
BH/BY 後再以基準及 PBO 篩選，只是保守的二次篩選，不保證原本的 FDR。
拆分假說可減少單一假說的 PBO 義務，但會增加世代的 m 與多重檢驗懲罰。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
import os
from itertools import combinations
from statistics import NormalDist
import uuid
from pathlib import Path
import re

GENESIS = "0" * 64
DEFAULT_EMBARGO_SECONDS = 7 * 86400
LEDGERS = ("preregistrations", "trials", "holdouts")
# 訓練段起點依 2026-10-18 的裁決（事件 RH-20261018-01）與取數起點同步提前到 2020-01-01；驗證段與兩段 holdout 不變。
DEFAULT_BOUNDARIES = (
    "2020-01-01T00:00:00Z", "2025-07-01T00:00:00Z",
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
                    embargo_seconds=DEFAULT_EMBARGO_SECONDS, max_lookback_seconds=0):
    """空窗一律從後一段開頭扣除；回看資料由未來資料載入器另行限制。"""
    if len(boundaries) != len(generations) + 3 or not generations:
        raise LedgerError("切分日期與 holdout 世代數不符")
    if len(set(generations)) != len(generations) or list(generations) != sorted(generations):
        raise LedgerError("每代只能綁一段 holdout")
    for generation in generations:
        _integer(generation, 1)
    gap = max(DEFAULT_EMBARGO_SECONDS, _number(label_period_seconds, 0),
              _number(max_holding_seconds, 0), _number(embargo_seconds, 0))
    lookback = _number(max_lookback_seconds, 0)
    dates = [_time(x) for x in boundaries]
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise LedgerError("切分重疊或順序錯誤")
    result = []
    for i, (start, end) in enumerate(zip(dates, dates[1:])):
        if i:
            start += timedelta(seconds=max(gap, lookback) if i >= 3 else gap)
        if start >= end:
            raise LedgerError("扣除空窗後沒有可用資料")
        result.append({"id": ("train", "validation")[i] if i < 2 else "holdout-" + str(generations[i-2]),
                       "kind": ("train", "validation")[i] if i < 2 else "holdout",
                       "generation": None if i < 2 else generations[i-2],
                       "start": _iso(start), "end": _iso(end)})
    return result


def _splits(record):
    segments = record["time_splits"]
    if not isinstance(segments, list) or len(segments) != 4:
        raise LedgerError("必須有訓練、驗證與兩段 holdout")
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
            # 第二段以後的暖機不得回到上一代 holdout。
            minimum_gap = max(gap, record["max_lookback_seconds"]) if i >= 3 else gap
            start = max(start, previous + timedelta(seconds=minimum_gap))
        if start >= end:
            raise LedgerError("扣除空窗後沒有可用資料")
        if i >= 2:
            generation = _integer(segment.get("generation"), 1)
            if generation != i-1 or generation in generations:
                raise LedgerError("holdout 世代重複或倒序")
            generations.add(generation)
        checked.append({**segment, "start": _iso(start), "end": _iso(end)})
        previous = end
    return checked


def _prereg(record):
    fields = ("hypothesis_id", "family", "economic_mechanism", "decision_period", "expected_holding_seconds",
              "expected_turnover", "pessimistic_cost_ratio", "data_range", "time_splits", "primary_metric",
              "candidate_thresholds", "multiple_testing", "max_lookback_seconds", "label_period_seconds",
              "max_holding_seconds", "selection", "split_rationale", "generation", "sharpe_frequency_seconds",
              "oos_protocol", "baselines", "falsification_rule")
    _required(record, fields)
    period = record["decision_period"]
    _required(period, ("unit", "value"))
    if period["unit"] not in ("second", "minute", "hour", "day") or _number(period["value"], 0) == 0:
        raise LedgerError("決策週期不合法")
    decision = _decision_seconds(record)
    if decision < 3600:
        _required(record, ("non_speed_edge",))
    for key in ("expected_holding_seconds", "expected_turnover", "pessimistic_cost_ratio", "max_lookback_seconds", "label_period_seconds", "max_holding_seconds"):
        _number(record[key], 0)
    if record["max_holding_seconds"] < record["expected_holding_seconds"] or record["label_period_seconds"] < decision:
        raise LedgerError("持有期或標籤期短於所屬週期")
    if _integer(record["generation"], 1) not in (1, 2):
        raise LedgerError("世代必須為 1 或 2")
    _integer(record["sharpe_frequency_seconds"], 1)
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
    if multiple["method"] not in ("BH", "BY") or not isinstance(members, list) or not all(isinstance(x, str) and x for x in members):
        raise LedgerError("多重檢驗須為 BH 或 BY 與非空假說集合")
    if len(set(members)) != len(members) or record["hypothesis_id"] not in members:
        raise LedgerError("家族成員重複或未含本假說")
    if sha256(sorted(members)) != _hash(multiple["members_sha256"]):
        raise LedgerError("家族成員雜湊不符")
    if not 0 < _number(multiple["fdr"], 0, 0.5) < 0.5:
        raise LedgerError("FDR 須介於 0 與 0.5")
    shared = [{**seg, "start": _iso(_range(seg)[0]), "end": _iso(_range(seg)[1])} for seg in record["time_splits"]]
    checked = {**record, "shared_time_splits": shared, "time_splits": _splits(record)}
    protocol = record["oos_protocol"]
    _required(protocol, ("scheme", "initial_train_seconds", "test_seconds", "step_seconds", "purge_seconds", "embargo_seconds"))
    if protocol["scheme"] not in ("expanding", "rolling"):
        raise LedgerError("未知的走動式樣本外協定")
    for key in ("initial_train_seconds", "test_seconds", "step_seconds", "purge_seconds", "embargo_seconds"):
        if _number(protocol[key], 0) == 0:
            raise LedgerError("協定秒數必須為正")
    gap = max(DEFAULT_EMBARGO_SECONDS, record["label_period_seconds"], record["max_holding_seconds"])
    if min(protocol["purge_seconds"], protocol["embargo_seconds"]) < gap:
        raise LedgerError("purge 或 embargo 不足")
    f = record["sharpe_frequency_seconds"]
    if protocol["step_seconds"] < protocol["test_seconds"] or protocol["test_seconds"] % f or protocol["step_seconds"] % f:
        raise LedgerError("測試窗須不重疊且與報酬頻率相容")
    baselines = record["baselines"]
    if not isinstance(baselines, list):
        raise LedgerError("基準須為清單")
    for item in baselines:
        _required(item, ("id", "kind"))
        if not isinstance(item["id"], str) or item["kind"] not in ("strategy_independent", "exposure_matched"):
            raise LedgerError("基準類別不合法")
    ids = [x["id"] for x in baselines]
    if len(set(ids)) != len(ids) or "no_trade" not in ids or len(ids) < 2:
        raise LedgerError("須含不交易與至少一個被動持有基準")
    if next(x for x in baselines if x["id"] == "no_trade")["kind"] != "strategy_independent":
        raise LedgerError("no_trade 必須與策略無關")
    _required(record["falsification_rule"], ("degradation_z",))
    _number(record["falsification_rule"]["degradation_z"], 0.5, 1.645)
    checked["baselines"] = sorted(baselines, key=lambda x: x["id"])
    checked["oos_protocol_sha256"] = sha256(protocol)
    checked["folds"] = walk_forward_folds(checked)
    if not checked["folds"]:
        raise LedgerError("樣本外摺表至少需要一折")
    oos_seconds = sum((_range(x["score_window"])[1]-_range(x["score_window"])[0]).total_seconds() for x in checked["folds"])
    lengths = {"out_of_sample": oos_seconds, **{x["id"]: (_range(x)[1]-_range(x)[0]).total_seconds() for x in checked["time_splits"][2:]}}
    independent = {k: v/_independence_seconds(checked) for k,v in lengths.items()}
    if independent["out_of_sample"] < 30:
        raise LedgerError("樣本外有效獨立期數少於 30")
    checked["effective_independent_periods"] = independent
    checked["sample_size_warning"] = [k for k,n in independent.items() if n < (100 if k == "out_of_sample" else 30)]
    checked["detectable_sharpe"] = _detectable(lengths, .05)
    return checked



def _decision_seconds(record):
    p = record['decision_period']
    return p['value'] * {'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400}[p['unit']]


def _independence_seconds(record):
    return max(_decision_seconds(record), record['max_holding_seconds'], record['label_period_seconds'])


def _detectable(lengths, alpha):
    return {k: (NormalDist().inv_cdf(1-alpha)+NormalDist().inv_cdf(.8))/math.sqrt(seconds/(365.25*86400)) for k,seconds in lengths.items()}


def _window(a, b):
    return {'start': _iso(a), 'end': _iso(b)}


def period_grid(window, frequency):
    """只包含完全落在半開區間內、與 UTC 網格對齊的一期。"""
    _integer(frequency, 1)
    a,b = _range(window)
    first = math.ceil(a.timestamp()/frequency)*frequency
    stop = math.floor(b.timestamp()/frequency)*frequency
    return list(range(first, stop, frequency))


def walk_forward_folds(record):
    s = _range(record['time_splits'][0])[0]
    e = _range(record['time_splits'][1])[1]
    p = record['oos_protocol']; g = max(p['purge_seconds'],p['embargo_seconds'])
    fit_end = s + timedelta(seconds=p['initial_train_seconds'])
    folds = []
    while fit_end + timedelta(seconds=g+p['test_seconds']) <= e:
        fit_start = s if p['scheme']=='expanding' else fit_end-timedelta(seconds=p['initial_train_seconds'])
        folds.append({'fit_window': _window(fit_start,fit_end),
                      'score_window': _window(fit_end+timedelta(seconds=g), fit_end+timedelta(seconds=g+p['test_seconds']))})
        fit_end += timedelta(seconds=p['step_seconds'])
    return folds


class ResearchLedger:
    """單一鎖內追加三本帳，所有 recorded_at 只來自建構時的時鐘。"""

    def __init__(self, out, *, clock=None):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self._lock():
            path = self.out/'ledger_id.json'
            if not path.exists():
                if any((self.out/(name+'.jsonl')).exists() for name in LEDGERS):
                    raise LedgerError('既有帳本缺 ledger_id，不可自動重新辨識')
                with path.open('xb') as stream:
                    stream.write(canonical({'ledger_id': str(uuid.uuid4())}))
                    stream.flush(); os.fsync(stream.fileno())
            value = json.loads(path.read_bytes())
            if set(value) != {'ledger_id'} or str(uuid.UUID(value['ledger_id'])) != value['ledger_id']:
                raise LedgerError('ledger_id 不合法')
            self.ledger_id = value['ledger_id']

    @contextmanager
    def _lock(self):
        with (self.out/'.ledger.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(lock, fcntl.LOCK_UN)

    @contextmanager
    def _write_lock(self):
        # 寫入或匯出鏈頭前，先補上中斷遺留的證偽判定；只用帳內的完成事件與序列，不需要原始的結束請求。
        with self._lock():
            self._recover_falsifications()
            yield

    def _now(self):
        value = self.clock()
        return _iso(_time(value if isinstance(value,str) else _iso(value)))

    def _read(self, name, pinned=None):
        path = self.out/(name+'.jsonl')
        raw = path.read_bytes() if path.exists() else b''
        if raw and not raw.endswith(b'\n'): raise LedgerError('帳本末筆不完整')
        previous, records, seen, at = GENESIS, [], {GENESIS}, None
        for index,line in enumerate(raw.splitlines(),1):
            try:
                row=json.loads(line)
                if set(row)!={'sequence','previous','payload','hash'}: raise ValueError('結構')
                unsigned={k:row[k] for k in ('sequence','previous','payload')}
                if type(row['sequence']) is not int or row['sequence']!=index or row['previous']!=previous or row['hash']!=sha256(unsigned): raise ValueError('鏈接')
                if canonical(row)!=line: raise ValueError('非標準化 JSON')
                stamp=_time(row['payload']['recorded_at'])
                if at is not None and stamp<at: raise ValueError('時間倒退')
                at=stamp
            except (ValueError,TypeError,KeyError) as exc: raise LedgerError(name+' 鏈被改寫或損壞') from exc
            previous=row['hash']; seen.add(previous); records.append(row)
        if pinned is not None and _hash(pinned) not in seen: raise LedgerError('找不到已提交鏈頭')
        return records

    def _append(self, name, payload, *, now=None):
        rows=self._read(name); at=now or self._now()
        if rows and _time(at)<_time(rows[-1]['payload']['recorded_at']): raise LedgerError('時鐘倒退')
        row={'sequence':len(rows)+1,'previous':self._head(rows),'payload':{**payload,'recorded_at':at}}
        row['hash']=sha256(row)
        # 同一鎖內保留完整舊前綴，原子發布追加後的整本帳，避免中斷留下半行。
        # replace 已成功但回報失敗時，重試仍可從完整的新鏈恢復。
        temporary=self.out/('.'+name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:
                for previous in rows: stream.write(canonical(previous)+b'\n')
                stream.write(canonical(row)+b'\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,self.out/(name+'.jsonl'))
            directory=os.open(self.out,os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return row['hash']

    @staticmethod
    def _head(rows): return rows[-1]['hash'] if rows else GENESIS

    def export_heads(self):
        # 匯出前會補上中斷遺留的證偽判定，因此可能追加 holdout 帳；只核對不寫入請用 verify_heads。
        with self._write_lock(): return {'ledger_id':self.ledger_id,**{name:self._head(self._read(name)) for name in LEDGERS}}

    def verify_heads(self, pinned):
        if not isinstance(pinned,dict) or set(pinned)!={'ledger_id',*LEDGERS} or pinned['ledger_id']!=self.ledger_id:
            raise LedgerError('ledger_id 或三本帳鏈頭不符')
        with self._lock(): return {'ledger_id':self.ledger_id,**{name:self._head(self._read(name,pinned[name])) for name in LEDGERS}}

    def data_access(self, hypothesis_id, trial_id=None):
        """重複查得已開啟的區間，不改 open_holdout 規則，也不是第二次開啟。

        呼叫者須先確認目錄與 ledger_id.json 存在才建構帳本。
        本版 U4 拒絕物化 holdout；未來啟用時，每次物化的 manifest
        雜湊必須記入試驗，才能追溯資料釋出。
        """
        with self._lock():
            events = {name: [row['payload'] for row in self._read(name)] for name in LEDGERS}
            registration = next((e['record'] for e in events['preregistrations']
                                 if e['action'] == 'preregister'
                                 and e['record']['hypothesis_id'] == hypothesis_id), None)
            if registration is None:
                raise LedgerError('假說必須先預登記')
            if trial_id is not None:
                if not any(e['action'] == 'begin_trial' and e['record']['trial_id'] == trial_id
                           and e['record']['hypothesis_id'] == hypothesis_id for e in events['trials']):
                    raise LedgerError('試驗不存在或不屬於本假說')
            elif any(e['action'] == 'withdrawn' and e['hypothesis_id'] == hypothesis_id
                     for e in events['preregistrations']):
                raise LedgerError('已撤回假說須綁定已開始的試驗')
            opening = next((e for e in events['holdouts'] if e['action'] == 'opened'
                            and e['generation'] == registration['generation']), None)
            return {
                'generation': registration['generation'],
                'time_splits': registration['time_splits'],
                'selection': registration['selection'],
                'out_of_sample': {'start': registration['time_splits'][0]['start'],
                                  'end': registration['time_splits'][1]['end']},
                'max_lookback_seconds': registration['max_lookback_seconds'],
                'holdout': opening['intervals'].get(hypothesis_id) if opening else None,
            }

    def trial_record(self, trial_id):
        """唯讀回傳 begin_trial 的完整身份及目前結束狀態，不觸發補寫。

        呼叫者須先確認帳本目錄及 ledger_id.json 存在；未結束時保留
        帳本既有的 aborted 預設狀態，以 finished 明確區分是否已結束。
        """
        with self._lock():
            events = {name: [row['payload'] for row in self._read(name)] for name in LEDGERS}
            record = next((e['record'] for e in events['trials']
                           if e['action'] == 'begin_trial' and e['record']['trial_id'] == trial_id), None)
            if record is None:
                raise LedgerError('試驗未開始')
            finish = next((e for e in reversed(events['trials'])
                           if e['action'] == 'finish_trial' and e['trial_id'] == trial_id), None)
            return {'record': record, 'finished': finish is not None,
                    'status': finish['status'] if finish else 'aborted'}

    def _events(self, name): return [r['payload'] for r in self._read(name)]

    def _registrations(self):
        return {r['record']['hypothesis_id']:r for r in self._events('preregistrations') if r['action']=='preregister'}

    def _registration(self, hypothesis_id):
        try: return self._registrations()[hypothesis_id]
        except KeyError as exc: raise LedgerError('假說必須先預登記') from exc

    def _withdrawn(self, hypothesis_id):
        return any(e['action']=='withdrawn' and e['hypothesis_id']==hypothesis_id for e in self._events('preregistrations'))

    def _generation_result(self, generation):
        return next((e for e in self._events('holdouts') if e['action']=='generation_result' and e['generation']==generation),None)

    def preregister(self, record):
        forbidden={'recorded_at','registered_at','oos_protocol_sha256','effective_independent_periods','detectable_sharpe','sample_size_warning','folds','shared_time_splits','power_estimate','sharpe','sr','dsr','p_value','passed','eligible'}
        if forbidden & set(record): raise LedgerError('不得提供帳本計算欄位或寫入時間')
        record=_prereg(json.loads(canonical(record)))
        with self._write_lock():
            regs=self._registrations(); g=record['generation']
            if record['hypothesis_id'] in regs: raise LedgerError('假說代號重複')
            if self._generation_result(g) or any(e['action']=='begin_trial' and e['record']['generation']==g for e in self._events('trials')):
                raise LedgerError('本世代已開始試驗或結算，禁止新增預登記')
            if any(e['action']=='opened' and e['generation']<g for e in self._events('holdouts')):
                raise LedgerError('早期 holdout 已開啟，禁止後代預登記')
            for old in regs.values():
                old=old['record']
                if old['shared_time_splits']!=record['shared_time_splits']:
                    raise LedgerError('全帳本切分邊界必須相同')
                if old['generation']==g and any(old[k]!=record[k] for k in ('multiple_testing','sharpe_frequency_seconds','baselines')):
                    raise LedgerError('同世代方法、FDR、成員、頻率或基準不一致')
            digest=sha256(record)
            self._append('preregistrations',{'action':'preregister','record':record,'record_sha256':digest})
            return digest

    def withdraw_hypothesis(self, hypothesis_id, reason):
        if not isinstance(reason,str) or not reason.strip(): raise LedgerError('撤回需要理由')
        with self._write_lock():
            reg=self._registration(hypothesis_id)['record']
            if self._withdrawn(hypothesis_id) or self._generation_result(reg['generation']): raise LedgerError('已撤回或結算')
            return self._append('preregistrations',{'action':'withdrawn','hypothesis_id':hypothesis_id,'reason':reason})

    def _trials(self):
        trials={}
        for event in self._events('trials'):
            if event['action']=='begin_trial':
                r=event['record']
                trials[r['trial_id']]={**r,'recorded_at':event['recorded_at'],'status':'aborted','finished':False}
            elif event['action']=='finish_trial':
                trials[event['trial_id']].update({k:v for k,v in event.items() if k not in ('action','recorded_at')})
                trials[event['trial_id']]['finished']=True
        return trials

    def _trial_identity(self, record):
        return {'variant_parameters_sha256':sha256(record['variant_parameters']),
                **{k:record[k] for k in ('evaluation_kind','role','parent_trial_id','data_window','fit_window','score_window')},
                'primary_trial_id':record.get('primary_trial_id')}

    def _plans(self, hypothesis_id=None):
        return [(e['hypothesis_id'],p) for e in self._events('preregistrations') if e['action']=='trial_plan'
                and (hypothesis_id is None or e['hypothesis_id']==hypothesis_id) for p in e['planned_trials']]

    def commit_trial_plan(self, hypothesis_id, planned_trials):
        with self._write_lock():
            reg=self._registration(hypothesis_id)['record']
            if reg['generation']!=2 or self._withdrawn(hypothesis_id) or self._generation_result(2):
                raise LedgerError('只有尚未撤回或結算的第二代可提交試驗計畫')
            if any(e['action']=='opened' for e in self._events('holdouts')):
                raise LedgerError('holdout 開啟後不得新增試驗計畫')
            if not isinstance(planned_trials,list) or not planned_trials: raise LedgerError('計畫須非空')
            plans=json.loads(canonical(planned_trials)); previous=[p for _,p in self._plans(hypothesis_id)]
            fields={'variant_parameters_sha256','evaluation_kind','role','parent_trial_id','data_window','fit_window','score_window','primary_trial_id'}
            trials=self._trials()
            for p in plans:
                if set(p)!=fields: raise LedgerError('試驗計畫身份欄位不完整')
                _hash(p['variant_parameters_sha256'])
                if p['evaluation_kind'] not in ('in_sample','out_of_sample','holdout_falsification') or p['role'] not in ('primary_oos','exploratory'):
                    raise LedgerError('計畫種類或角色不符')
                if p['role']=='primary_oos' and p['evaluation_kind']!='out_of_sample': raise LedgerError('主試驗必須樣本外')
                if p['evaluation_kind']!='holdout_falsification':
                    parent=trials.get(p['parent_trial_id'])
                    if parent is None or parent['generation']>=reg['generation']: raise LedgerError('計畫缺較早世代親代')
                for key in ('data_window','fit_window','score_window'): _range(p[key])
                if any(p==old for old in previous): raise LedgerError('計畫身份重複')
                previous.append(p)
            if sum(p['role']=='primary_oos' for p in previous)>1: raise LedgerError('計畫只能有一個主試驗')
            return self._append('preregistrations',{'action':'trial_plan','hypothesis_id':hypothesis_id,'planned_trials':plans})

    def _validate_trial(self, record, reg, trials):
        fields={'trial_id','hypothesis_id','generation','parent_trial_id','variant_parameters','data_window','manifest_sha256','data_files',
                'code_commit','cost_model','fill_model','configuration','configuration_sha256','engine','dependencies','time_semantics',
                'random_seed','sharpe_frequency','evaluation_kind','role','fit_window','score_window'}
        optional={'folds','oos_protocol_sha256','primary_trial_id'}
        if not fields<=set(record) or set(record)-fields-optional: raise LedgerError('試驗身份缺漏或含結果、統計量、寫入時間')
        _required(record, fields-{'parent_trial_id','random_seed','variant_parameters','dependencies'})
        if not isinstance(record['trial_id'],str): raise LedgerError('試驗代號須為字串')
        if record['trial_id'] in trials: raise LedgerError('試驗代號重複')
        if _integer(record['generation'],1)!=reg['generation']: raise LedgerError('世代與預登記不符')
        for key in ('variant_parameters','dependencies','configuration','data_files'):
            if not isinstance(record[key],dict): raise LedgerError('身份子欄位須為物件')
        for key in ('manifest_sha256','configuration_sha256'): _hash(record[key])
        for value in record['data_files'].values(): _hash(value)
        if not isinstance(record['code_commit'],str) or not re.fullmatch(r'[0-9a-f]{40}',record['code_commit']): raise LedgerError('程式 commit 格式錯誤')
        for key in ('cost_model','fill_model','engine'): _required(record[key],('id','version'))
        if set(record['configuration'])!={'strategy_parameters','cost_model_parameters'}: raise LedgerError('設定身份缺漏')
        if sha256(record['configuration'])!=record['configuration_sha256']: raise LedgerError('設定雜湊不符')
        _required(record['time_semantics'],('known_at','fill_at','simulated_latency_ms'))
        _number(record['time_semantics']['simulated_latency_ms'],0)
        if record['random_seed'] is not None: _integer(record['random_seed'])
        _required(record['sharpe_frequency'],('unit','seconds','annualized'))
        if type(record['sharpe_frequency']['seconds']) is not int or record['sharpe_frequency']['seconds']!=reg['sharpe_frequency_seconds'] or record['sharpe_frequency']['annualized'] is not False:
            raise LedgerError('Sharpe 頻率須與登記同頻且不年化')
        kind=record['evaluation_kind']; role=record['role']
        if kind not in ('in_sample','out_of_sample','holdout_falsification') or role not in ('exploratory','primary_oos'):
            raise LedgerError('試驗種類或角色不符')
        if role=='primary_oos' and kind!='out_of_sample': raise LedgerError('主試驗須為樣本外')
        if kind!='in_sample' and record.get('oos_protocol_sha256')!=reg['oos_protocol_sha256']: raise LedgerError('協定雜湊不符')
        parent=record['parent_trial_id']
        if kind!='holdout_falsification' and reg['generation']>1 and parent is None: raise LedgerError('後代試驗缺親代')
        if parent is not None and (parent not in trials or trials[parent]['generation']>=reg['generation']): raise LedgerError('親代須為較早世代')
        allowed=(_range(reg['time_splits'][0])[0],_range(reg['time_splits'][1])[1])
        fit,score,data=(_range(record[k]) for k in ('fit_window','score_window','data_window'))
        if not allowed[0]<=fit[0]<fit[1]<=allowed[1]: raise LedgerError('擬合窗超出樣本外範圍')
        if not data[0]<=min(fit[0],score[0]) or not max(fit[1],score[1])<=data[1]: raise LedgerError('資料窗未涵蓋擬合與評分窗')
        if kind!='holdout_falsification':
            if not allowed[0]<=data[0]<data[1]<=allowed[1] or not allowed[0]<=score[0]<score[1]<=allowed[1]: raise LedgerError('試驗資料窗超出允許範圍')
            if self._generation_result(reg['generation']): raise LedgerError('世代已結算')
            if any(t['hypothesis_id']==record['hypothesis_id'] and t['role']=='primary_oos' for t in trials.values()): raise LedgerError('主試驗已開始，不可新增試驗')
            if kind=='out_of_sample':
                if record.get('folds')!=reg['folds']: raise LedgerError('摺表與帳本產生的不符')
                if score!=(_range(reg['folds'][0]['score_window'])[0],_range(reg['folds'][-1]['score_window'])[1]): raise LedgerError('評分窗未精確涵蓋樣本外摺表')
        else:
            primary=trials.get(record.get('primary_trial_id'))
            if parent is not None or primary is None or primary['role']!='primary_oos' or primary['hypothesis_id']!=record['hypothesis_id'] or primary['generation']!=reg['generation']:
                raise LedgerError('證偽主試驗身份不符')
            if any(t['hypothesis_id']==record['hypothesis_id'] and t['evaluation_kind']=='holdout_falsification' for t in trials.values()): raise LedgerError('每個候選只能證偽一次')
            if sha256(record['variant_parameters'])!=sha256(primary['variant_parameters']) or record['oos_protocol_sha256']!=primary['oos_protocol_sha256'] or record['sharpe_frequency']['seconds']!=primary['sharpe_frequency']['seconds']:
                raise LedgerError('證偽參數、協定或頻率與主試驗不符')
            opening=next((e for e in self._events('holdouts') if e['action']=='opened' and e['generation']==reg['generation']),None)
            if opening is None or record['hypothesis_id'] not in opening['intervals'] or record['score_window']!=opening['intervals'][record['hypothesis_id']]: raise LedgerError('holdout 未授權或區間不符')
            ds,de=_range(reg['data_range'])
            if not ds<=data[0]<data[1]<=de: raise LedgerError('證偽資料窗超出登記')

    def begin_trial(self, record):
        record=json.loads(canonical(record)); record.setdefault('role','exploratory')
        with self._write_lock():
            reg_event=self._registration(record.get('hypothesis_id')); reg=reg_event['record']; trials=self._trials()
            if self._withdrawn(record['hypothesis_id']): raise LedgerError('假說已撤回')
            self._validate_trial(record,reg,trials)
            identity=self._trial_identity(record)
            if any(e['action']=='opened' and e['generation']<reg['generation'] for e in self._events('holdouts')):
                if not any(p==identity for _,p in self._plans(record['hypothesis_id'])): raise LedgerError('只接受 holdout 開啟前的計畫身份')
                if any(t['hypothesis_id']==record['hypothesis_id'] and self._trial_identity(t)==identity for t in trials.values()): raise LedgerError('計畫身份只能使用一次')
            at=self._now()
            if _time(at)<=_time(reg_event['recorded_at']): raise LedgerError('試驗必須嚴格晚於預登記')
            return self._append('trials',{'action':'begin_trial','record':{**record,'started_at':at,'variant_parameters_sha256':identity['variant_parameters_sha256'],'preregistration_sha256':reg_event['record_sha256']}},now=at)

    def _periods(self, trial, reg):
        if trial['evaluation_kind']=='out_of_sample':
            return sorted({p for f in reg['folds'] for p in period_grid(f['score_window'],reg['sharpe_frequency_seconds'])})
        return period_grid(trial['score_window'],reg['sharpe_frequency_seconds'])

    def _series(self, sha):
        _hash(sha)
        try: raw=(self.out/'series'/(sha+'.json')).read_bytes()
        except OSError as exc: raise LedgerError('已存序列缺失或無法讀取：'+sha) from exc
        if hashlib.sha256(raw).hexdigest()!=sha: raise LedgerError('已存序列雜湊不符')
        return json.loads(raw)

    def _store_series(self, descriptor, periods, reg):
        if not isinstance(descriptor,dict) or set(descriptor)!={'path','sha256'}: raise LedgerError('序列須含路徑與 SHA-256')
        expected=_hash(descriptor['sha256']); raw=Path(descriptor['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected: raise LedgerError('提交序列雜湊不符')
        try: value=json.loads(raw)
        except (ValueError,UnicodeError) as exc: raise LedgerError('無效序列 JSON') from exc
        if canonical(value)!=raw or not isinstance(value,dict) or set(value)!={'period_seconds','filled_periods','returns'}: raise LedgerError('序列必須為標準化 JSON')
        if _integer(value['period_seconds'],1)!=reg['sharpe_frequency_seconds']: raise LedgerError('序列頻率不符')
        rows=value['returns']
        if not isinstance(rows,list) or any(not isinstance(row,list) or len(row)!=2 or type(row[0]) is not int for row in rows): raise LedgerError('序列格式不符')
        if [row[0] for row in rows]!=periods: raise LedgerError('序列期數網格不符')
        for row in rows: _number(row[1])
        if _integer(value['filled_periods'])>len(rows): raise LedgerError('填補期數超過總期數')
        if len(rows)<2: raise LedgerError('序列至少兩期')
        self._persist_series(expected,raw)
        return expected,value

    def _persist_series(self, sha, raw):
        directory=self.out/'series'; directory.mkdir(exist_ok=True)
        path=directory/(sha+'.json')
        if path.exists():
            if path.read_bytes()!=raw: raise LedgerError('既有序列雜湊不符')
        else:
            # 只在帳本鎖內發布完整序列；中斷的暫存檔不會成為帳本引用。
            temporary=directory/(sha+'.tmp')
            with temporary.open('wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,path)
            # 序列目錄也要落盤，避免完成事件已落盤而序列檔遺失。
            handle=os.open(directory,os.O_RDONLY)
            try: os.fsync(handle)
            finally: os.close(handle)

    def finish_trial(self, trial_id, result):
        result=json.loads(canonical(result))
        allowed={'status','returns','baselines','result_summary','ended_at','produced_periods'}
        if set(result)-allowed: raise LedgerError('結束紀錄不得改身份、統計量、判定或寫入時間')
        _required(result,('status','result_summary','ended_at'))
        if result['status'] not in ('completed','failed','aborted'): raise LedgerError('狀態不合法')
        with self._write_lock():
            trials=self._trials(); trial=trials.get(trial_id)
            if trial is None: raise LedgerError('試驗未開始')
            reg=self._registration(trial['hypothesis_id'])['record']; kind=trial['evaluation_kind']
            if trial['finished']:
                if kind!='holdout_falsification' or trial.get('completion_request_sha256')!=sha256(result):
                    raise LedgerError('試驗已結束，不得修改結果')
                return self._complete_falsification(trial,reg)
            if kind!='holdout_falsification' and self._generation_result(reg['generation']): raise LedgerError('世代已結算')
            at=self._now(); ended=_time(result['ended_at'])
            if not _time(trial['recorded_at'])<=ended<=_time(at): raise LedgerError('結束時間超出開始與結束寫入時間')
            periods=self._periods(trial,reg)
            produced=result.get('produced_periods',len(periods) if result.get('returns') else 0)
            _integer(produced)
            if kind!='in_sample' and (result['status']=='completed' or produced>=2) and not result.get('returns'): raise LedgerError('試驗缺報酬序列')
            stored={'action':'finish_trial','trial_id':trial_id,'status':result['status'],'result_summary':result['result_summary'],'ended_at':_iso(ended),'produced_periods':produced,'returns_sha256':None,'baseline_sha256':{},'statistics':None}
            if result.get('returns'):
                sha,value=self._store_series(result['returns'],periods,reg)
                if produced!=len(periods): raise LedgerError('產出期數與序列不符')
                stored['returns_sha256']=sha
                stored['statistics']=statistics_from_returns([r[1] for r in value['returns']],period_seconds=reg['sharpe_frequency_seconds'],independent_seconds=_independence_seconds(reg))
                stored['filled_periods']=value['filled_periods']
                if kind=='out_of_sample':
                    supplied=result.get('baselines',{}); expected={b['id'] for b in reg['baselines']}-{'no_trade'}
                    if not isinstance(supplied,dict) or set(supplied)!=expected: raise LedgerError('基準序列清單不完整或企圖提供 no_trade')
                    for baseline in reg['baselines']:
                        key=baseline['id']
                        if key=='no_trade':
                            zero={'period_seconds':reg['sharpe_frequency_seconds'],'filled_periods':0,'returns':[[p,0.0] for p in periods]}
                            raw=canonical(zero); bs=hashlib.sha256(raw).hexdigest(); self._persist_series(bs,raw)
                        else: bs,_=self._store_series(supplied[key],periods,reg)
                        if baseline['kind']=='strategy_independent':
                            for old in trials.values():
                                if old['generation']==reg['generation'] and old['evaluation_kind']=='out_of_sample' and old.get('folds')==trial['folds'] and old.get('baseline_sha256',{}).get(key) not in (None,bs):
                                    raise LedgerError('策略無關基準在同世代同摺表必須相同')
                        stored['baseline_sha256'][key]=bs
            elif result.get('baselines'): raise LedgerError('無報酬序列時不得提供基準')
            if kind=='holdout_falsification': stored['completion_request_sha256']=sha256(result)
            self._append('trials',stored,now=at)
            if kind=='holdout_falsification':
                return self._complete_falsification({**trial,**stored},reg)
            return stored

    def _recover_falsifications(self):
        # 完成事件已寫入、證偽判定尚未寫入時中斷：依完成事件補上判定，每筆試驗只補一次。
        done={e['trial_id'] for e in self._events('holdouts') if e['action']=='falsification_result'}
        for trial in self._trials().values():
            if trial['evaluation_kind']=='holdout_falsification' and trial['finished'] and trial['trial_id'] not in done:
                try: self._complete_falsification(trial,self._registration(trial['hypothesis_id'])['record'])
                except LedgerError as exc: raise LedgerError('試驗 '+trial['trial_id']+' 的證偽判定無法補上：'+str(exc)) from exc

    def _complete_falsification(self, trial, reg):
        # trials 的完成事件是恢復點；重試不重新接受來源檔或呼叫者的統計量。
        previous=next((e for e in self._events('holdouts') if e['action']=='falsification_result' and e['trial_id']==trial['trial_id']),None)
        if previous is not None: return {k:v for k,v in previous.items() if k!='recorded_at'}
        statistics=None
        if trial.get('returns_sha256'):
            series=self._series(trial['returns_sha256'])
            statistics=statistics_from_returns([r[1] for r in series['returns']],period_seconds=reg['sharpe_frequency_seconds'],independent_seconds=_independence_seconds(reg))
        verdict=self._falsification({**trial,'statistics':statistics},reg)
        self._append('holdouts',verdict)
        return verdict

    def _counts(self, trials):
        actual=[t for t in trials.values() if t['evaluation_kind']!='holdout_falsification']
        pending=[]
        regs=self._registrations()
        for hid,p in self._plans():
            if p['evaluation_kind']!='holdout_falsification' and not any(t['hypothesis_id']==hid and self._trial_identity(t)==p for t in actual):
                pending.append({'hypothesis_id':hid,'generation':regs[hid]['record']['generation']})
        return actual+pending

    def _pbo_inputs(self, hypothesis_id, trials):
        reg=self._registration(hypothesis_id)['record']
        return {tid:self._series(t['returns_sha256']) for tid,t in trials.items()
                if t['hypothesis_id']==hypothesis_id and t['evaluation_kind']=='out_of_sample' and t['finished']
                and t['status']=='completed' and t.get('folds')==reg['folds'] and t.get('returns_sha256')}

    def pbo_status(self, hypothesis_id):
        with self._lock():
            self._registration(hypothesis_id); trials=self._trials()
            count=sum(t['hypothesis_id']==hypothesis_id for t in self._counts(trials))
            series=self._pbo_inputs(hypothesis_id,trials)
            return {'required':count>=10,'non_holdout_trial_count':count,'N':len(series)}

    def family_trial_count(self, family):
        with self._lock():
            regs=self._registrations()
            return sum(regs[t['hypothesis_id']]['record']['family']==family for t in self._counts(self._trials()))

    def close_generation(self, generation):
        if _integer(generation,1) not in (1,2): raise LedgerError('世代須為1或2')
        with self._write_lock():
            if self._generation_result(generation): raise LedgerError('每代只能結算一次')
            regs={h:e['record'] for h,e in self._registrations().items() if e['record']['generation']==generation}
            if not regs: raise LedgerError('世代沒有假說')
            members=sorted(regs); binding=regs[members[0]]['multiple_testing']
            if sorted(binding['members'])!=members: raise LedgerError('尚未完成全世代家族成員預登記')
            trials=self._trials(); counts=self._counts(trials); k=len(counts); results={}
            for hid,reg in regs.items():
                primary=next((t for t in trials.values() if t['hypothesis_id']==hid and t['role']=='primary_oos'),None)
                withdrawn=self._withdrawn(hid)
                if not withdrawn and (primary is None or not primary['finished']): raise LedgerError('每個未撤回假說須有已結束主試驗')
                stats=primary.get('statistics') if primary else None
                h={'primary_trial_id':primary['trial_id'] if primary else None,'T':stats['T'] if stats else 0,
                   'T_eff':stats['t_eff'] if stats else None,'sr':stats['sr'] if stats else None,'sr0':None,'v':None,'n_v':0,
                   'dsr':None,'p_value':1.0,'p_value_reason':None,'baseline_excess':{},'pbo':None,'pbo_series_count':0,
                   'statistics':stats,'p_value_algorithm':'dsr_bailey_lopez_de_prado_v1','variance_trial_ids':[]}
                reason=None
                if withdrawn: reason='withdrawn'
                elif primary['status']!='completed': reason=primary['status']
                elif stats is None: reason='missing_series'
                elif stats['sample_std']==0: reason='zero_standard_deviation'
                elif stats['t_eff']<=1: reason='effective_n_not_above_one'
                elif _denominator(stats)<=0: reason='nonpositive_denominator'
                elif primary.get('filled_periods',0)>.05*stats['T']: reason='excess_filled_periods'
                if stats and stats['t_eff']>1:
                    # V 的樣本只取 SR 有定義的已完成樣本外試驗；K 與 V 依結算當下的全帳本內容決定。
                    pool={tid:t['statistics']['sr'] for tid,t in trials.items()
                          if t['evaluation_kind']=='out_of_sample' and t['finished'] and t['status']=='completed'
                          and t.get('oos_protocol_sha256')==primary.get('oos_protocol_sha256')
                          and t['sharpe_frequency']['seconds']==primary['sharpe_frequency']['seconds']
                          and t.get('statistics') and t['statistics']['sr'] is not None}
                    values=list(pool.values()); n=len(values); variance=None
                    if n>=2:
                        mean=math.fsum(values)/n; variance=math.fsum((v-mean)**2 for v in values)/(n-1)
                    floor=1/(stats['t_eff']-1); v=max(variance or 0,floor)
                    sr0=math.sqrt(v)*_maximum_normal(k) if k else 0
                    h.update(v=v,n_v=n,sr0=sr0,variance_sample=variance,variance_floor=floor,
                             expected_max_standard_normal=_maximum_normal(k) if k else 0,variance_trial_ids=sorted(pool))
                    if reason is None:
                        h['dsr']=_psr(stats,sr0); h['p_value']=1-h['dsr']
                h['p_value_reason']=reason
                for baseline in reg['baselines']:
                    key=baseline['id']; excess={'sr':None,'t_eff':None,'psr0':0.0}
                    if primary and primary.get('returns_sha256') and key in primary.get('baseline_sha256',{}):
                        own=self._series(primary['returns_sha256'])['returns']; other=self._series(primary['baseline_sha256'][key])['returns']
                        if [r[0] for r in own]!=[r[0] for r in other]: raise LedgerError('基準期數不符')
                        values=[x[1]-y[1] for x,y in zip(own,other)]
                        es=statistics_from_returns(values,period_seconds=reg['sharpe_frequency_seconds'],independent_seconds=_independence_seconds(reg))
                        excess={'sr':es['sr'],'t_eff':es['t_eff'],'psr0':_psr(es),'statistics':es}
                    h['baseline_excess'][key]=excess
                results[hid]=h
            adjusted=_adjust_p({h:r['p_value'] for h,r in results.items()},binding['method'])
            for hid,h in results.items():
                h['adjusted_p_value']=adjusted[hid]; h['accepted']=adjusted[hid]<=binding['fdr']
                needs=sum(t['hypothesis_id']==hid for t in counts)>=10
                h['pbo_required']=needs
                if h['accepted'] and needs:
                    series=self._pbo_inputs(hid,trials); h['pbo_series_count']=len(series)
                    if len(series)>=10 and min(len(s['returns']) for s in series.values())>=32:
                        h['pbo']=cscv_pbo({tid:[r[1] for r in value['returns']] for tid,value in series.items()})
                h['eligible']=h['accepted'] and all(b['psr0']>=.95 for b in h['baseline_excess'].values()) and (not needs or h['pbo'] is not None and h['pbo']<.5)
            m=len(regs); harmonic=math.fsum(1/i for i in range(1,m+1)) if binding['method']=='BY' else 1
            power={}
            for hid,reg in regs.items():
                lengths={key:n*_independence_seconds(reg) for key,n in reg['effective_independent_periods'].items()}
                power[hid]=_detectable(lengths,binding['fdr']/m/harmonic)
            result={'action':'generation_result','generation':generation,'K':k,'K_generation':sum(t['generation']==generation for t in counts),
                    'method':binding['method'],'fdr':binding['fdr'],'m':m,'members_sha256':sha256(members),
                    'hypotheses':results,'eligible':sorted(h for h,r in results.items() if r['eligible']),
                    'detectable_sharpe':power,'planned_unstarted_count':len(counts)-len([t for t in trials.values() if t['evaluation_kind']!='holdout_falsification'])}
            self._append('holdouts',result)
            return result

    def seal_holdout(self, hypothesis_id, segment_id):
        with self._write_lock():
            reg=self._registration(hypothesis_id)['record']
            segment=next((s for s in reg['time_splits'] if s['kind']=='holdout' and s['id']==segment_id),None)
            if segment is None or segment['generation']!=reg['generation']: raise HoldoutDenied('只能封存本假說世代的 holdout')
            events=self._events('holdouts'); interval={k:segment[k] for k in ('start','end')}
            if any(e['action']=='sealed' and e['hypothesis_id']==hypothesis_id and e['segment_id']==segment_id for e in events): raise HoldoutDenied('同假說同段不得重複封存')
            if any(e['action']=='opened' and e['generation']==reg['generation'] for e in events): raise HoldoutDenied('此世代已開啟')
            for event in events:
                if event['action']=='sealed' and event['generation']!=reg['generation']:
                    a,b=_range(event['interval']); c,d=_range(interval)
                    if a<d and c<b: raise HoldoutDenied('不同世代 holdout 區間重疊')
            return self._append('holdouts',{'action':'sealed','hypothesis_id':hypothesis_id,'segment_id':segment_id,'generation':reg['generation'],'interval':interval})

    def open_holdout(self, generation, candidate_trial_ids):
        if _integer(generation,1) not in (1,2): raise HoldoutDenied('世代不合法')
        with self._write_lock():
            events=self._events('holdouts'); result=self._generation_result(generation); reason=None
            valid=isinstance(candidate_trial_ids,list) and all(isinstance(x,str) and x for x in candidate_trial_ids)
            if valid:
                # 無法標準化的字串（例如孤立的 surrogate）同樣視為不合法輸入，拒絕事件只記型別，不記原值。
                try: canonical(candidate_trial_ids)
                except LedgerError: valid=False
            if any(e['action']=='opened' and e['generation']==generation for e in events): reason='同世代已開啟，不得再次讀取'
            elif not valid: reason='候選須為試驗代號清單'
            elif result is None: reason='本世代尚未結算'
            elif generation==2 and not any(e['action']=='opened' and e['generation']==1 for e in events): reason='第一代尚未開啟'
            candidates=sorted(candidate_trial_ids) if valid else None
            if reason is None:
                expected=sorted(result['hypotheses'][h]['primary_trial_id'] for h in result['eligible'])
                if candidates!=expected: reason='候選必須恰好等於全部合格主試驗'
            intervals={}
            if reason is None:
                for hid in result['eligible']:
                    reg=self._registration(hid)['record']
                    segment=next(s for s in reg['time_splits'] if s['kind']=='holdout' and s['generation']==generation)
                    if not any(e['action']=='sealed' and e['hypothesis_id']==hid and e['segment_id']==segment['id'] for e in events):
                        reason='候選尚未封存'; break
                    intervals[hid]={k:segment[k] for k in ('start','end')}
            event={'action':'denied' if reason else 'opened','generation':generation,'candidate_trial_ids':candidates,'candidates_sha256':sha256(candidates) if valid else None}
            if not valid: event.update(candidate_input_valid=False,candidate_input_type=type(candidate_trial_ids).__name__)
            if reason:
                self._append('holdouts',{**event,'reason':reason})
                raise HoldoutDenied(reason)
            head=self._append('holdouts',{**event,'intervals':intervals})
            return {'intervals':intervals,'candidates_sha256':event['candidates_sha256'],'holdouts_head':head}

    def _falsification(self, trial, reg):
        reference=self._generation_result(reg['generation'])['hypotheses'][trial['hypothesis_id']]
        stats=trial.get('statistics'); sr=stats['sr'] if stats else None
        denominator=_denominator(stats) if stats else None
        se=math.sqrt(denominator/(stats['t_eff']-1)) if denominator is not None and denominator>0 and stats['t_eff']>1 else None
        sr_ref=reference['sr']-reference['sr0']; z=reg['falsification_rule']['degradation_z']
        positive=sr is not None and sr>0
        same=sr is not None and sr*reference['sr']>0
        stable=se is not None and sr>=sr_ref-z*se
        return {'action':'falsification_result','generation':reg['generation'],'hypothesis_id':trial['hypothesis_id'],
                'primary_trial_id':trial['primary_trial_id'],'trial_id':trial['trial_id'],'statistics':stats,
                'sr_h':sr,'t_eff_h':stats['t_eff'] if stats else None,'gamma3_h':stats['skewness'] if stats else None,
                'gamma4_h':stats['kurtosis'] if stats else None,'sr_ref':sr_ref,'se_h':se,'degradation_z':z,
                'cost_positive':positive,'same_direction':same,'not_degraded':stable,
                'passed':trial['status']=='completed' and positive and same and stable}




def statistics_from_returns(values, *, period_seconds, independent_seconds):
    """未年化 SR、未校偏樣本矩與 Bartlett 有效期數。"""
    _integer(period_seconds,1)
    if _number(independent_seconds,0)==0: raise LedgerError('獨立週期必須為正')
    x=[_number(v) for v in values]; n=len(x)
    if n<2: raise LedgerError('序列至少需要兩期')
    mean=math.fsum(x)/n
    # 各期相同時標準差視為 0；避免浮點殘差讓常數序列得到極大的 SR。
    centered=[0.0]*n if max(x)==min(x) else [v-mean for v in x]
    squares=math.fsum(v*v for v in centered); m2=squares/n
    sd=math.sqrt(squares/(n-1)); q=math.floor(4*(n/100)**(2/9))
    # 浮點在整數邊界可能差一；依 q^9·100^2 ≤ 4^9·n^2 的整數比較校正。
    while (q+1)**9*10000<=262144*n*n: q+=1
    while q>0 and q**9*10000>262144*n*n: q-=1
    correlations=[math.fsum(centered[t]*centered[t-k] for t in range(k,n))/squares if squares else 0 for k in range(1,q+1)]
    factor=1+2*math.fsum((1-k/(q+1))*rho for k,rho in enumerate(correlations,1))
    effective=min(n/max(factor,1),n*period_seconds/independent_seconds)
    skew=math.fsum(v**3 for v in centered)/n/m2**1.5 if m2 else None
    kurt=math.fsum(v**4 for v in centered)/n/m2**2 if m2 else None
    result={'T':n,'mean':mean,'sample_std':sd,'sr':mean/sd if sd and effective>1 else None,
            'skewness':skew,'kurtosis':kurt,'excess_kurtosis':kurt-3 if kurt is not None else None,
            'q':q,'autocorrelations':correlations,'bartlett_factor':factor,'t_eff':effective,
            'effective_n_algorithm':'bartlett_effective_n_v1'}
    canonical(result)
    return result


def _denominator(stats):
    sr=stats['sr']
    return None if sr is None else 1-stats['skewness']*sr+(stats['kurtosis']-1)/4*sr*sr


def _psr(stats, threshold=0):
    denominator=_denominator(stats)
    if denominator is None or denominator<=0 or stats['t_eff']<=1: return 0.0
    return NormalDist().cdf((stats['sr']-threshold)*math.sqrt(stats['t_eff']-1)/math.sqrt(denominator))


def _maximum_normal(k):
    if k==1: return 0.0
    gamma=.5772156649015329
    return (1-gamma)*NormalDist().inv_cdf(1-1/k)+gamma*NormalDist().inv_cdf(1-1/(k*math.e))


def _adjust_p(values, method):
    ordered=sorted(values,key=lambda k:(values[k],k)); m=len(ordered)
    harmonic=math.fsum(1/i for i in range(1,m+1)) if method=='BY' else 1
    running=1.0; adjusted={}
    for rank in range(m,0,-1):
        key=ordered[rank-1]; running=min(running,values[key]*m*harmonic/rank); adjusted[key]=running
    return adjusted


def cscv_pbo(series):
    """固定16塊的 CSCV；用塊內總和與平方和計算全部12870組。"""
    ids=sorted(series); n=len(ids)
    if n<2: raise LedgerError('CSCV 至少需要兩個序列')
    length=len(series[ids[0]])
    if length<32 or any(len(series[k])!=length for k in ids): raise LedgerError('CSCV 共同期數不足或不一致')
    size=length//16
    blocks=[]
    for key in ids:
        x=[_number(v) for v in series[key]]
        blocks.append([(len(part),math.fsum(part),math.fsum(v*v for v in part)) for part in
                       (x[i*size:(i+1)*size] if i<15 else x[i*size:] for i in range(16))])
    def score(parts, choice):
        count=sum(parts[i][0] for i in choice); total=math.fsum(parts[i][1] for i in choice)
        variance=max(0.0,(math.fsum(parts[i][2] for i in choice)-total*total/count)/(count-1))
        return total/count/math.sqrt(variance) if variance else 0.0
    negative=0; total=0
    for inside in combinations(range(16),8):
        outside=tuple(i for i in range(16) if i not in inside)
        # ids 已依字典序排列；max 遇同分保留第一個。
        winner=max(range(n),key=lambda j:score(blocks[j],inside))
        scores=[score(parts,outside) for parts in blocks]; selected=scores[winner]
        lower=sum(v<selected for v in scores); tied=sum(v==selected for v in scores)
        rank=lower+(tied+1)/2
        omega=rank/(n+1); logit=math.log(omega/(1-omega))
        negative+=logit<=0; total+=1
    return negative/total


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    actions=('heads','verify','preregister','commit_trial_plan','begin_trial','finish_trial',
             'withdraw_hypothesis','close_generation','seal_holdout','open_holdout','pbo_status')
    parser.add_argument('action',choices=actions)
    parser.add_argument('--record',help='JSON 輸入；preregister/begin_trial 為紀錄本身，其餘為具名參數物件')
    args=parser.parse_args(argv)
    try:
        book=ResearchLedger(args.out)
        if args.action=='heads': result=book.export_heads()
        else:
            if not args.record: parser.error('此動作需要 --record')
            value=json.loads(Path(args.record).read_bytes())
            if args.action=='verify': result=book.verify_heads(value)
            elif args.action in ('preregister','begin_trial'): result=getattr(book,args.action)(value)
            else: result=getattr(book,args.action)(**value)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True,allow_nan=False))
    except (LedgerError,OSError,ValueError,TypeError,KeyError) as exc:
        parser.exit(2,str(exc)+'\n')


if __name__=='__main__':
    main()
