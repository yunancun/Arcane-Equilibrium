"""DV3 recorder tools for the approved 2026-10-22 verification standard.

Recorder-only API; never import into a hypothesis. No automatic fetch, credentials,
holdout activation, sampling replacement, or write to the P3b source. Public
artifact-producing entry points return the exact section 8.4 handoff. The caller
supplies frozen source identities and the dispatched scope, URL list and limits.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
import sys
import ssl
import time
import threading
from urllib.parse import urlsplit, parse_qsl
from urllib.request import build_opener, ProxyHandler, HTTPSHandler, HTTPRedirectHandler, Request
from urllib.error import HTTPError

DAY = 86_400_000
HOUR = 3_600_000
TRAIN_START = 1577836800000
TRAIN_END = 1751328000000
SEED = 20261022
TIERS = ('GE_100M', 'GE_10M', 'GE_1M', 'NO_OPEN')
STANDARD = 'docs/execution_plan/2026-10-22--r8-stage2-data-verification-standard.md'
V2 = 'v2-terminal-suffix-20261022'
_V1_STANDARDS=('d0fbf9ff02d080027d575eb6488f2c552c3a583485b8c685166fe0ef94b2af98',
               'ba65fbca3b9230ad1807b82c923e9e60ab870edbe5c1e0d5090ebce99b06f6d0',
               '125901d0341487bd058be70e7cc2ed27be7c3be270a45d05587e471104b7cacf',
               'ad80220cd6dc3f8dc5c451c6281aa9f1b2acf7fbb47bc80ed21eb3905710110c')


class InvalidInput(ValueError):
    """Only a fixed reason code, never source values, in errors."""


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise InvalidInput('INVALID_FIELDS')


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise InvalidInput('INVALID_INTEGER')
    return value


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise InvalidInput('INVALID_SHA256')
    return value


def _symbol(value):
    if not isinstance(value, str) or not re.fullmatch('[A-Z0-9]+USDT', value):
        raise InvalidInput('INVALID_SYMBOL')
    return value


def _readable(value):
    _keys(value, 'start end')
    start, end = _integer(value['start']), _integer(value['end'])
    # No host proof exists here to activate holdout or a new generation.
    if not TRAIN_START <= start < end <= TRAIN_END:
        raise InvalidInput('SCOPE_NOT_AUTHORIZED')
    return start, end


def _path(root, name):
    root = Path(root).absolute()
    if not isinstance(name, str) or not name or '\\' in name:
        raise InvalidInput('UNSAFE_PATH')
    p = Path(name)
    if p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise InvalidInput('UNSAFE_PATH')
    target = root / p
    if any(x.is_symlink() for x in (target, *target.parents)):
        raise InvalidInput('UNSAFE_PATH')
    return target


def _write(root, name, data):
    p = _path(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write(data)
        f.flush()
        import os
        os.fsync(f.fileno())


def _handoff(root, primary=None, files=None, reasons=()):
    files = files or {}
    return dict(schema_version='r8_verification_handoff_v1',
                status='BLOCKED' if reasons or primary is None else 'READY',
                artifact_root=str(root), primary_file=primary,
                primary_sha256=files[primary]['sha256'] if primary else None,
                files=files, reason_codes=sorted(set(reasons)))


def _emit(root, name, data, rows, reasons=(), extras=None):
    files = dict(extras or {})
    _write(root, name, data)
    files[name] = dict(sha256=sha(data), rows=rows)
    return _handoff(root, name, files, reasons)


def _decimal(text):
    if not isinstance(text, str) or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',text):
        raise InvalidInput('INVALID_DECIMAL')
    try:
        n = Decimal(text)
    except InvalidOperation:
        raise InvalidInput('INVALID_DECIMAL') from None
    if not n.is_finite():
        raise InvalidInput('INVALID_DECIMAL')
    return n


def _policy(manifest,version='v1-strict',standard_sha=None):
    standard = Path(__file__).resolve().parents[3] / STANDARD
    current=sha(standard.read_bytes())
    if standard_sha is not None and standard_sha not in ((current,)+_V1_STANDARDS if version=='v1-strict' else (current,)):raise InvalidInput('POLICY_MISMATCH')
    result=dict(schema_version='r8_data_verification_policy_v1',
                standard_sha256=current if standard_sha is None else standard_sha, approval_event='RH-20261022-04',
                p3b_manifest_sha256=_hash(manifest),
                listing=dict(x_pct='50',y_pct='20',z_pct='20',cooling_days=7,
                             quantity='hourly_base_volume_daily_mean',variation='mean_relative_difference',
                             stage_end_ranges=[[1,3],[7,15],[15,30]]),
                sampling=dict(seed=SEED,base_per_stratum=300,max_per_stratum=900,
                              max_expansions=1,confidence='0.95',upper_limit='0.025'),
                turnover=dict(window_days=12,thresholds=['1000000','10000000','100000000'],
                              trigger_pct='5',general='exchange_reported',suspect='sum_hourly_reported'),
                l4_price_threshold_pct='1')
    if version==V2:result.update(schema_version='r8_data_verification_policy_v2',approval_event='RH-20261022-05',volume_semantics_policy=V2)
    elif version!='v1-strict':raise InvalidInput('POLICY_MISMATCH')
    return result


@dataclass(frozen=True)
class CSVSource:
    symbol: str
    dataset: str
    interval: str
    relative_path: str
    sha256: str


def _sample312(rng,population,k):
    """CPython 3.12 Random.sample's counts=None algorithm, frozen locally.

    Uses the same MT19937 integer seed/getrandbits and both pool/set branches;
    avoids changing draws with the host Python's future sample implementation.
    Algorithm source: Python 3.12 Lib/random.py (PSF license).
    """
    n=len(population); result=[None]*k; setsize=21
    if k>5:
        setsize+=4**math.ceil(math.log(k*3,4))
    if n<=setsize:
        pool=list(population)
        for i in range(k):
            j=rng._randbelow(n-i)
            result[i]=pool[j]; pool[j]=pool[n-i-1]
    else:
        selected=set()
        for i in range(k):
            j=rng._randbelow(n)
            while j in selected:
                j=rng._randbelow(n)
            selected.add(j); result[i]=population[j]
    return result


def _rows(root, source, start, end):
    data = _path(root, source.relative_path).read_bytes()
    if sha(data) != _hash(source.sha256):
        raise InvalidInput('SOURCE_HASH_MISMATCH')
    stream = gzip.GzipFile(fileobj=io.BytesIO(data)) if source.relative_path.endswith('.gz') else io.BytesIO(data)
    with stream:
        if stream.readline().rstrip(b'\r\n') != b'timestamp,open,high,low,close,volume,turnover':
            raise InvalidInput('INVALID_CSV_HEADER')
        for raw in stream:
            # Opaque bytes first: no market-column decoding outside readable.
            stamp, separator, rest = raw.partition(b',')
            if not separator or not re.fullmatch(rb'[0-9]+', stamp):
                raise InvalidInput('INVALID_TIMESTAMP')
            t = int(stamp)
            if start <= t < end:
                yield t, rest


def build_sample_plan(source_root, artifact_root, sources, *, readable,
                      p3b_manifest_sha256, truncated_days=()):
    """Freeze a whole draw sequence before publishing sample_plan.json.

    ``sources`` are recorder-selected frozen original CSVs, not corrected views.
    ``truncated_days`` contains (symbol, UTC day start) from known market windows.
    Only timestamp metadata and prior readable daily turnover are inspected.
    """
    try:
        start,end = _readable(readable)
        if Path(artifact_root).resolve().is_relative_to(Path(source_root).resolve()):
            # A sibling output is recommended; a separate child directory is
            # permitted for constructed fixtures but never an existing source.
            if Path(artifact_root).resolve()==Path(source_root).resolve():
                raise InvalidInput('OUTPUT_OVERLAPS_SOURCE')
        manifest_bytes=_path(source_root,'manifest.json').read_bytes()
        if sha(manifest_bytes)!=_hash(p3b_manifest_sha256):
            raise InvalidInput('MANIFEST_HASH_MISMATCH')
        manifest=json.loads(manifest_bytes)
        if not isinstance(manifest.get('files'),dict) or not isinstance(manifest.get('universe'),dict):
            raise InvalidInput('INVALID_MANIFEST')
        sources=list(sources)
        required_sources=set()
        for name,meta in manifest['files'].items():
            if not isinstance(meta,dict):
                raise InvalidInput('INVALID_MANIFEST')
            if meta.get('dataset')!='kline' or meta.get('interval') not in ('D','60'):
                continue
            _path(source_root,name)
            coverage=meta.get('coverage')
            if coverage is not None:
                if not isinstance(coverage,list) or len(coverage)!=2:
                    raise InvalidInput('INVALID_MANIFEST_COVERAGE')
                a,b=(_integer(t) for t in coverage)
                if a>=b:
                    raise InvalidInput('INVALID_MANIFEST_COVERAGE')
                if b<=start or a>=end:
                    continue
            required_sources.add(name)
        if not required_sources <= {s.relative_path for s in sources}:
            raise InvalidInput('INCOMPLETE_MANIFEST_SOURCES')
        policy = encoded(_policy(p3b_manifest_sha256))
        hourly, daily, first, seen, windows = {}, {}, {}, set(), {}
        truncated = set(truncated_days)
        for symbol,day in truncated:
            _symbol(symbol)
            if _integer(day) % DAY:
                raise InvalidInput('INVALID_DAY')
        for source in sources:
            _symbol(source.symbol)
            if source.dataset != 'kline' or source.interval not in ('60','D'):
                raise InvalidInput('INVALID_DATASET')
            meta=manifest['files'].get(source.relative_path,{})
            if any(meta.get(k)!=getattr(source,k) for k in ('symbol','dataset','interval','sha256')):
                raise InvalidInput('SOURCE_NOT_IN_FROZEN_MANIFEST')
            window=manifest['universe'].get(source.symbol)
            if not isinstance(window,dict):
                raise InvalidInput('MISSING_MARKET_WINDOW')
            launch=window.get('launch_time',window.get('launchTime'))
            if 'launch_time' in window and 'launchTime' in window and str(window['launch_time'])!=str(window['launchTime']):
                raise InvalidInput('CONFLICTING_MARKET_WINDOW')
            stamps=[]
            for stamp in (launch,window.get('deliveryTime')):
                if type(stamp) is str and re.fullmatch('[0-9]+',stamp):
                    stamp=int(stamp)
                _integer(stamp);stamps.append(stamp)
                if stamp and stamp%DAY:
                    truncated.add((source.symbol,stamp//DAY*DAY))
            windows[source.symbol]=tuple(stamps)
            key=(source.symbol,source.interval)
            if key in seen:
                raise InvalidInput('DUPLICATE_SOURCE')
            seen.add(key)
            for t, raw in _rows(source_root,source,start,end):
                day=t//DAY*DAY
                if source.interval=='60':
                    first[source.symbol]=min(first.get(source.symbol,t),t)
                    hourly.setdefault((source.symbol,day),set()).add(t)
                elif t % DAY==0 and t+DAY<=end:
                    # Preserve duplicates as invalid history, never choose first.
                    daily.setdefault((source.symbol,t),[]).append(raw)
        strata={}
        reasons=set()
        for (symbol,day),grid in sorted(hourly.items()):
            if day<start or day+DAY>end:
                reasons.add('SCOPE_INCOMPLETE'); continue
            launch,delivery=windows[symbol]
            if day+DAY<=launch or delivery and day>=delivery or (symbol,day) in truncated or not set(range(day,day+DAY,HOUR)) <= grid:
                reasons.add('PARTIAL_OR_GAPPED'); continue
            tier='NO_OPEN'
            origin=max(first[symbol],launch)
            first_full=(origin+DAY-1)//DAY*DAY
            if day-12*DAY>=max(first_full,start):
                amounts=[]
                for previous in range(day-12*DAY,day,DAY):
                    rows=daily.get((symbol,previous),[])
                    if not rows:
                        amounts.append(Fraction(0)); continue
                    if len(rows)!=1:
                        break
                    fields=rows[0].rstrip(b'\r\n').split(b',')
                    if len(fields)!=6:
                        break
                    try:
                        n=_decimal(fields[-1].decode('ascii'))
                    except (InvalidInput,UnicodeError):
                        break
                    if n<0:
                        break
                    amounts.append(Fraction(n))
                if len(amounts)==12:
                    amounts.sort()
                    median=(amounts[5]+amounts[6])/2
                    tier=next((name for name,threshold in zip(TIERS,(100000000,10000000,1000000)) if median>=threshold),'NO_OPEN')
                else:
                    reasons.add('UNCLASSIFIABLE_HISTORY')
            else:
                reasons.add('INSUFFICIENT_HISTORY')
            year=datetime.fromtimestamp(day//1000,timezone.utc).year
            strata.setdefault((year,tier),[]).append((symbol,day))
        rng=random.Random(SEED)
        plan=dict(schema_version='r8_verification_sample_plan_v1',policy_sha256=sha(policy),
                  p3b_manifest_sha256=p3b_manifest_sha256,readable=dict(readable),seed=SEED,strata=[])
        for (year,tier),population in sorted(strata.items(),key=lambda p:(p[0][0],TIERS.index(p[0][1]))):
            population.sort()
            draws=_sample312(rng,population,min(900,len(population)))
            plan['strata'].append(dict(year=year,tier=tier,population_size=len(population),
                                      base_size=min(300,len(population)),max_size=min(900,len(population)),
                                      draws=[dict(rank=i,symbol=s,day_start=d) for i,(s,d) in enumerate(draws,1)]))
        data=encoded(plan)
        # Exclusive, durable seal is written before any sample is released.
        _write(artifact_root,'sample_plan.sha256',(sha(data)+'\n').encode())
        _write(artifact_root,'policy.json',policy)
        # Nonfatal population exclusions/history reasons are retained separately;
        # they do not purport to be a sampling acceptance verdict.
        note=('\n'.join(sorted(reasons))+'\n').encode()
        _write(artifact_root,'population_notes.txt',note)
        extras={'policy.json':dict(sha256=sha(policy),rows=1),
                'sample_plan.sha256':dict(sha256=sha((sha(data)+'\n').encode()),rows=1),
                'population_notes.txt':dict(sha256=sha(note),rows=len(reasons))}
        return _emit(artifact_root,'sample_plan.json',data,1,() if strata else ('EMPTY_POPULATION',),extras)
    except (InvalidInput,OSError,EOFError,ValueError,TypeError,AttributeError) as exc:
        return _handoff(artifact_root,reasons=(str(exc) if isinstance(exc,InvalidInput) else 'IO_ERROR',))


def hypergeometric_upper(N, n, x, alpha):
    """Exact numerical primitive, not an artifact handoff; returns a rational."""
    for value in (N,n,x):
        _integer(value)
    if not 0 < n <= N or x > n or not isinstance(alpha,Fraction) or not 0 < alpha < 1:
        raise InvalidInput('INVALID_STATISTICS')
    if n==N:
        return Fraction(x,N)
    denominator=math.comb(N,n)
    def admissible(M):
        numerator=sum(math.comb(M,k)*math.comb(N-M,n-k)
                      for k in range(max(0,n-(N-M)), min(x,M,n)+1))
        return numerator*alpha.denominator >= denominator*alpha.numerator
    lo,hi=x,N
    while lo<hi:
        mid=(lo+hi+1)//2
        if admissible(mid):
            lo=mid
        else:
            hi=mid-1
    return Fraction(lo,N)


def _json(data):
    def pairs(items):
        obj={}
        for key,value in items:
            if key in obj:
                raise InvalidInput('DUPLICATE_KEY')
            obj[key]=value
        return obj
    def bad(_):
        raise InvalidInput('INVALID_JSON_NUMBER')
    try:
        value=json.loads(data.decode('utf-8'),object_pairs_hook=pairs,parse_constant=bad)
    except (ValueError,UnicodeError):
        raise InvalidInput('INVALID_JSON') from None
    if encoded(value)!=data:
        raise InvalidInput('NONCANONICAL_JSON')
    return value


def _load_plan(root,*,allow_empty=False):
    data=_path(root,'sample_plan.json').read_bytes()
    if _path(root,'sample_plan.sha256').read_bytes() != (sha(data)+'\n').encode():
        raise InvalidInput('PLAN_SEAL_MISMATCH')
    p=_json(data)
    _keys(p,'schema_version policy_sha256 p3b_manifest_sha256 readable seed strata')
    if p['schema_version']!='r8_verification_sample_plan_v1' or type(p['seed']) is not int or p['seed']!=SEED:
        raise InvalidInput('INVALID_PLAN')
    start,end=_readable(p['readable'])
    policy=_path(root,'policy.json').read_bytes()
    supplied=_json(policy)
    if not isinstance(supplied,dict):raise InvalidInput('POLICY_MISMATCH')
    if sha(policy)!=_hash(p['policy_sha256']) or policy!=encoded(_policy(p['p3b_manifest_sha256'],standard_sha=supplied.get('standard_sha256'))):
        raise InvalidInput('POLICY_MISMATCH')
    if not isinstance(p['strata'],list) or not p['strata'] and not allow_empty:
        raise InvalidInput('EMPTY_POPULATION')
    seen=set(); prior=None
    for s in p['strata']:
        _keys(s,'year tier population_size base_size max_size draws')
        year=_integer(s['year'])
        if s['tier'] not in TIERS:
            raise InvalidInput('INVALID_TIER')
        order=(year,TIERS.index(s['tier']))
        if prior is not None and order<=prior:
            raise InvalidInput('INVALID_STRATA_ORDER')
        prior=order
        N=_integer(s['population_size'],1)
        if _integer(s['base_size'])!=min(300,N) or _integer(s['max_size'])!=min(900,N):
            raise InvalidInput('INVALID_SAMPLE_SIZE')
        if not isinstance(s['draws'],list) or len(s['draws'])!=s['max_size']:
            raise InvalidInput('INVALID_DRAWS')
        for rank,d in enumerate(s['draws'],1):
            _keys(d,'rank symbol day_start')
            _symbol(d['symbol']); day=_integer(d['day_start'])
            key=(d['symbol'],day)
            if _integer(d['rank'],1)!=rank or key in seen or day%DAY or not start<=day<day+DAY<=end or datetime.fromtimestamp(day//1000,timezone.utc).year!=year:
                raise InvalidInput('INVALID_DRAW')
            seen.add(key)
    return p,sha(data)


_CORRECTION_KEYS='schema_version correction_id symbol dataset interval timestamp field original_value candidate_value corrected_value unit formula evidence_kind source_refs coverage_status order_status rule_ids decision reason_code row_action policy_sha256 approval_event supersedes'
_FINDING_KEYS='schema_version finding_id symbol dataset interval timestamp field rule_id reason_code source_refs details'
_VERIFICATION_KEYS='schema_version status policy_sha256 p3b_manifest_sha256 sample_plan_sha256 previous_corrections_sha256 review_refs tool_commit readable counts files reason_codes'
_SOURCE_KEYS='kind relative_path url sha256 row request_id list_index byte_start byte_end trade_id line_sha256'
_FIELDS=('open','high','low','close','volume','turnover')


def _refs(refs, evidence_root, verified, missing_trades=None):
    if not isinstance(refs,list):
        raise InvalidInput('INVALID_SOURCE_REFS')
    orders=[]
    for ref in refs:
        _keys(ref,_SOURCE_KEYS)
        if ref['kind'] not in ('raw','csv','trade','instruments','policy','plan','report'):
            raise InvalidInput('INVALID_SOURCE_KIND')
        if ref['relative_path'] is not None:
            path=_path(evidence_root,ref['relative_path']); digest=_hash(ref['sha256'])
            identity=(path,digest)
            if identity not in verified and not (missing_trades is not None and ref['kind']=='trade' and ref['relative_path'] in missing_trades):
                try:
                    # Cross-range sources are opaque: verify bytes, never decode
                    # market fields to authenticate a source identity.
                    with path.open('rb') as source:
                        actual=hashlib.sha256()
                        for chunk in iter(lambda:source.read(1024*1024),b''):
                            actual.update(chunk)
                except OSError:
                    if missing_trades is None or ref['kind']!='trade':
                        raise InvalidInput('SOURCE_EVIDENCE_UNAVAILABLE') from None
                    missing_trades.add(ref['relative_path'])
                else:
                    if actual.hexdigest()!=digest:
                        raise InvalidInput('SOURCE_EVIDENCE_HASH_MISMATCH')
                    verified.add(identity)
        elif ref['sha256'] is not None:
            raise InvalidInput('INVALID_SOURCE_REF')
        for name in ('row','list_index','byte_start','byte_end'):
            if ref[name] is not None:
                _integer(ref[name],1 if name=='row' else 0)
        for name in ('url','request_id','trade_id'):
            if ref[name] is not None and not isinstance(ref[name],str):
                raise InvalidInput('INVALID_SOURCE_REF')
        if ref['line_sha256'] is not None:
            _hash(ref['line_sha256'])
        if ref['byte_start'] is not None and ref['byte_end'] is not None and ref['byte_end']<ref['byte_start']:
            raise InvalidInput('INVALID_SOURCE_REF')
        orders.append((ref['kind'],ref['relative_path'] or '',*(ref[k] if ref[k] is not None else -1 for k in ('row','list_index','byte_start'))))
    if orders!=sorted(orders):
        raise InvalidInput('INVALID_SOURCE_REF_ORDER')



def _raw_spans(data):
    """Locate native list entries without decoding out-of-scope market values."""
    matches=list(re.finditer(rb'"list"\s*:\s*\[',data))
    if len(matches)!=1:
        raise InvalidInput('SOURCE_ROW_SCHEMA')
    start=matches[0].end(); depth=0; quoted=False; escaped=False; item=None; spans=[]
    for i in range(start,len(data)):
        c=data[i]
        if quoted:
            if escaped: escaped=False
            elif c==92: escaped=True
            elif c==34: quoted=False
        elif c==34: quoted=True
        elif c in (91,123): depth+=1
        elif c in (93,125):
            if c==93 and depth==0:
                if item is not None: spans.append((item,i))
                return spans,json.loads(data[:start]+data[i:])
            depth-=1
        if item is None and c not in b' \t\r\n,': item=i
        if not quoted and depth==0 and c==44:
            if item is None: raise InvalidInput('SOURCE_ROW_SCHEMA')
            spans.append((item,i));item=None
    raise InvalidInput('SOURCE_ROW_SCHEMA')


class _SourceRows:
    """Bind completed decisions to immutable originals, keeping source bytes opaque
    until the referenced identity and timestamp are inside the admitted window.
    Recorder packaging copies originals plus their pinned manifest/request log
    into the bundle; it does not rewrite SourceRefs or the original manifest.
    """
    def __init__(self,root,plan):
        self.root=root;self.plan=plan;self.cache={};self.manifest=None

    def data(self,ref):
        key=ref['relative_path']
        if key not in self.cache:
            self.cache[key]=_path(self.root,key).read_bytes()
        return self.cache[key]

    def load_manifest(self):
        if self.manifest is None:
            try: data=_path(self.root,'manifest.json').read_bytes()
            except OSError: raise InvalidInput('SOURCE_MANIFEST_UNAVAILABLE') from None
            if sha(data)!=self.plan['p3b_manifest_sha256']:
                raise InvalidInput('SOURCE_MANIFEST_HASH_MISMATCH')
            self.manifest=json.loads(data)
        return self.manifest

    def csv_meta(self,ref):
        meta=self.load_manifest()['files'].get(ref['relative_path'],{})
        if meta.get('sha256')!=ref['sha256'] or meta.get('dataset')!='kline':
            raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
        return meta

    def raw_identity(self,ref,query):
        manifest=self.load_manifest()
        if ref['relative_path']==f"raw/{ref['request_id']}.json":
            if 'requests' not in self.cache:
                data=_path(self.root,'requests.jsonl').read_bytes()
                if sha(data)!=manifest.get('request_log_sha256'):
                    raise InvalidInput('SOURCE_REQUEST_LOG_HASH_MISMATCH')
                requests=[json.loads(line) for line in data.splitlines()]
                if len({r['request_id'] for r in requests})!=len(requests):
                    raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
                self.cache['requests']={str(r['request_id']):r for r in requests}
            r=self.cache['requests'].get(ref['request_id'],{})
            params={k:str(v) for k,v in r.get('params',{}).items()}
            if (r.get('raw_sha256')!=ref['sha256'] or r.get('endpoint')!='/v5/market/kline'
                or params!=query or r.get('http_status')!=200 or r.get('retCode')!=0):
                raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
            metas=[m for m in manifest['files'].values() if m.get('symbol')==query['symbol']
                   and m.get('dataset')=='kline' and m.get('interval')==query['interval']]
            if not any(r['request_id'] in m.get('source_request_ids',m.get('request_ids',[])) for m in metas):
                raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
        else:
            if 'inventory' not in self.cache:
                data=_path(self.root,'download_inventory.jsonl').read_bytes()
                self.cache['inventory']=[_json(line) for line in data.splitlines(keepends=True)]
            matches=[r for r in self.cache['inventory'] if r['request_id']==ref['request_id']]
            if len(matches)!=1:
                raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
            r=matches[0]
            if (any(r[k]!=ref[k] for k in ('url','sha256','relative_path')) or r['status']!='AVAILABLE'
                or r['source_kind']!='bybit_minute' or r['symbol']!=query['symbol'] or r['interval']!=query['interval']):
                raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')

    def bind(self,row):
        delta={'D':DAY,'60':HOUR,'1':60000}[row['interval']]
        start=row['timestamp'];end=start+delta; original_found=False
        for ref in row['source_refs']:
            kind=ref['kind']
            if kind not in ('csv','raw','trade'):
                continue
            if ref['relative_path'] is None:
                raise InvalidInput('SOURCE_ROW_UNAVAILABLE')
            data=self.data(ref)
            if kind=='raw':
                url=urlsplit(ref['url'] or ''); q=dict(parse_qsl(url.query))
                if (url.scheme!='https' or url.hostname!='api.bybit.com' or url.path!='/v5/market/kline'
                    or q.get('category')!='linear' or q.get('symbol')!=row['symbol']
                    or q.get('interval') not in ('D','60','1')):
                    raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
                self.raw_identity(ref,q)
                source_interval=q['interval']
                cache_key=('spans',ref['relative_path'])
                if cache_key not in self.cache: self.cache[cache_key]=_raw_spans(data)
                spans,header=self.cache[cache_key]
                index=ref['list_index']
                if index is None or index>=len(spans) or tuple(spans[index])!=(ref['byte_start'],ref['byte_end']):
                    raise InvalidInput('SOURCE_ROW_POSITION_MISMATCH')
                a,z=spans[index];line=data[a:z]
                if (ref['row']!=data[:a].count(b'\n')+1 or header.get('retCode')!=0
                    or header.get('result',{}).get('symbol')!=row['symbol']
                    or header['result'].get('category')!='linear'):
                    raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
                match=re.match(rb'\s*\[\s*"([0-9]+)"\s*,',line)
                if not match: raise InvalidInput('SOURCE_ROW_TIMESTAMP_MISMATCH')
                stamp=int(match[1])
            else:
                cache_key=('lines',ref['relative_path'])
                if cache_key not in self.cache:
                    decoded=gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data
                    self.cache[cache_key]=decoded.splitlines(keepends=True)
                lines=self.cache[cache_key]
                if kind=='trade':
                    date=datetime.fromtimestamp(start//1000,timezone.utc).strftime('%Y-%m-%d')
                    if ref['url']!=f'https://public.bybit.com/trading/{row["symbol"]}/{row["symbol"]}{date}.csv.gz':
                        raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
                    # The full-file reference accompanies individual witnesses.
                    if ref['row'] is None:
                        if ref['line_sha256'] is not None: raise InvalidInput('SOURCE_ROW_POSITION_MISMATCH')
                        continue
                number=ref['row']
                if number is None or number<2 or number>len(lines):
                    raise InvalidInput('SOURCE_ROW_UNAVAILABLE')
                line=lines[number-1];fields=line.rstrip(b'\r\n').split(b',')
                if kind=='csv':
                    if lines[0].rstrip(b'\r\n')!=b'timestamp,open,high,low,close,volume,turnover':
                        raise InvalidInput('SOURCE_ROW_SCHEMA')
                    meta=self.csv_meta(ref);source_interval=meta.get('interval')
                    if meta.get('symbol')!=row['symbol'] or source_interval not in ('D','60','1'):
                        raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
                    if not re.fullmatch(rb'[0-9]+',fields[0]): raise InvalidInput('SOURCE_ROW_TIMESTAMP_MISMATCH')
                    stamp=int(fields[0])
                else:
                    header=next(csv.reader([lines[0].decode('utf-8')]))
                    if len(set(header))!=len(header) or not {'timestamp','symbol','trdMatchID'}<=set(header) or len(fields)!=len(header):
                        raise InvalidInput('SOURCE_ROW_SCHEMA')
                    if fields[header.index('symbol')].decode('ascii')!=row['symbol']:
                        raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
                    stamp=Fraction(_decimal(fields[header.index('timestamp')].decode('ascii')))*1000
                    source_interval=None
            if ref['line_sha256'] is None or sha(line)!=ref['line_sha256']:
                raise InvalidInput('SOURCE_LINE_HASH_MISMATCH')
            if not self.plan['readable']['start']<=stamp<self.plan['readable']['end'] or not start<=stamp<end:
                raise InvalidInput('SOURCE_ROW_TIMESTAMP_MISMATCH')
            if source_interval is not None:
                source_delta={'D':DAY,'60':HOUR,'1':60000}[source_interval]
                if source_delta>delta or stamp%source_delta or stamp+source_delta>end:
                    raise InvalidInput('SOURCE_ROW_IDENTITY_MISMATCH')
                values=json.loads(line) if kind=='raw' else next(csv.reader([line.decode('utf-8')]))
                if len(values)!=7 or any(not isinstance(v,str) for v in values):
                    raise InvalidInput('SOURCE_ROW_SCHEMA')
                if source_interval==row['interval']:
                    if stamp!=start: raise InvalidInput('SOURCE_ROW_TIMESTAMP_MISMATCH')
                    # CSV is the original adjudicated value. Raw may retain a
                    # documented representation difference; minute bars are raw.
                    if kind=='csv' or row['interval']=='1':
                        if values[1+_FIELDS.index(row['field'])]!=row['original_value']:
                            raise InvalidInput('SOURCE_ORIGINAL_VALUE_MISMATCH')
                        original_found=True
            elif next(csv.reader([line.decode('utf-8')]))[header.index('trdMatchID')]!=ref['trade_id']:
                raise InvalidInput('SOURCE_TRADE_ID_MISMATCH')
        if not original_found:
            raise InvalidInput('SOURCE_ORIGINAL_ROW_MISSING')

class _AdjudicationEvidence:
    """Authenticate the L3 proof, without trusting PASS/UNIQUE declarations."""
    def __init__(self,sources,findings,report_sha):
        self.sources=sources;self.report_sha=report_sha;self.findings={};self.totals={};self.hours={}
        for f in findings:
            key=(f['symbol'],f['interval'],f['timestamp'],f['field'],f['rule_id'])
            self.findings.setdefault(key,[]).append(f)

    def trade_totals(self,ref,symbol,day):
        key=(ref['relative_path'],ref['sha256'],symbol,day)
        if key in self.totals:return self.totals[key]
        self.totals[key]=None
        data=self.sources.data(ref)
        data=gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data
        totals={};ids=set();previous=None;direction=set()
        for r in csv.DictReader(io.StringIO(data.decode('utf-8'))):
            t=Fraction(_decimal(r['timestamp']))*1000
            if not day<=t<day+DAY or not self.sources.plan['readable']['start']<=t<self.sources.plan['readable']['end']:
                return None
            if r['symbol']!=symbol:return None
            price=Fraction(_decimal(r['price']));size=Fraction(_decimal(r['size']))
            if not r['trdMatchID'] or r['trdMatchID'] in ids or price<=0 or size<=0 or r.get('side') not in ('Buy','Sell'):return None
            ids.add(r['trdMatchID'])
            if previous is not None and t!=previous:direction.add(t>previous)
            previous=t
            if len(direction)>1:return None
            for window in (('D',day),('60',int(t//HOUR)*HOUR)):
                a=totals.setdefault(window,dict(volume=Fraction(0),count=0,first=t,last=t,open={price},close={price},high=price,low=price,groups={}))
                a['volume']+=size;a['count']+=1;a['high']=max(a['high'],price);a['low']=min(a['low'],price)
                a['groups'].setdefault(t,[]).append((size,r['trdMatchID']))
                if t<a['first']:a['first']=t;a['open']={price}
                elif t==a['first']:a['open'].add(price)
                if t>a['last']:a['last']=t;a['close']={price}
                elif t==a['last']:a['close'].add(price)
        self.totals[key]=totals
        return totals

    @staticmethod
    def trade_refs(refs,original):
        identity=(original['relative_path'],original['sha256'],original['url'])
        matched=[r for r in refs if r['kind']=='trade' and (r['relative_path'],r['sha256'],r['url'])==identity]
        return any(r['row'] is None for r in matched) and any(r['row'] is not None and r['trade_id'] and r['line_sha256'] for r in matched)

    def hour_complete(self,symbol,t,original,aggregate):
        key=(symbol,t,original['relative_path'],original['sha256'])
        if key in self.hours:return self.hours[key]
        self.hours[key]=False
        fs=self.findings.get((symbol,'60',t,'volume','C3_QUANTITY'),[])
        if len(fs)!=1 or fs[0]['reason_code']!='COVERAGE_RECONCILED' or not aggregate:return False
        f=fs[0];d={x['name']:x['value'] for x in f['details']}
        if not self.trade_refs(f['source_refs'],original):return False
        if not all(isinstance(d.get(k),str) for k in ('reported_volume','trade_volume','trade_count','first_timestamp_ms','last_timestamp_ms')):return False
        if (Fraction(_decimal(d.get('reported_volume')))!=aggregate['volume']
            or Fraction(_decimal(d.get('trade_volume')))!=aggregate['volume']
            or d.get('trade_count')!=str(aggregate['count'])
            or Fraction(_decimal(d.get('first_timestamp_ms')))!=aggregate['first']
            or Fraction(_decimal(d.get('last_timestamp_ms')))!=aggregate['last']):return False
        self.sources.bind(dict(symbol=symbol,interval='60',timestamp=t,field='volume',original_value=d['reported_volume'],source_refs=f['source_refs']))
        self.hours[key]=True
        return True

    def complete(self,row):
        refs=row['source_refs'];symbol=row['symbol'];t=row['timestamp'];day=t//DAY*DAY
        originals=[r for r in refs if r['kind']=='trade' and r['row'] is None and r['relative_path'] is not None]
        if len(originals)!=1 or not self.trade_refs(refs,originals[0]):return False
        if not any(r['kind']=='report' and r['relative_path']=='findings.jsonl' and r['sha256']==self.report_sha for r in refs):return False
        totals=self.trade_totals(originals[0],symbol,day)
        if not totals:return False
        a=totals.get((row['interval'],t))
        if not a or row['candidate_value'] is None:return False
        candidate=Fraction(_decimal(row['candidate_value']));expected=a.get(row['field'])
        if expected is None or (expected!={candidate} if isinstance(expected,set) else expected!=candidate):return False
        lines=self.sources.cache[('lines',originals[0]['relative_path'])]
        header=next(csv.reader([lines[0].decode('utf-8')]))
        witnesses=[]
        for ref in refs:
            if ref['kind']=='trade' and ref['row'] is not None and ref['relative_path']==originals[0]['relative_path']:
                values=next(csv.reader([lines[ref['row']-1].decode('utf-8')]))
                witnesses.append((Fraction(_decimal(values[header.index('timestamp')]))*1000,
                                  Fraction(_decimal(values[header.index('price')]))))
        if not all(any(stamp==a[edge] for stamp,_ in witnesses) for edge in ('first','last')):return False
        if row['field'] in ('high','low') and not any(price==candidate for _,price in witnesses):return False
        if row['interval']=='D':
            manifest=self.sources.load_manifest()
            first=min((m.get('first_timestamp',day) for m in manifest['files'].values()
                       if m.get('symbol')==symbol and m.get('dataset')=='kline' and m.get('interval')=='60'),default=day)
            delivery=int(manifest.get('universe',{}).get(symbol,{}).get('deliveryTime',0))
            start=max(day,first);end=min(day+DAY,((delivery+HOUR-1)//HOUR)*HOUR) if delivery else day+DAY
            times=list(range(start,end,HOUR))
            if {stamp for interval,stamp in totals if interval=='60'}!=set(times):return False
        else:times=[t]
        if not times or not all(self.hour_complete(symbol,h,originals[0],totals.get(('60',h))) for h in times):return False
        fs=self.findings.get((symbol,row['interval'],t,row['field'],'C5_REBUILD'),[])
        if len(fs)!=1 or fs[0]['reason_code']!='SOURCE_COMPARISON':return False
        f=fs[0];d={x['name']:x['value'] for x in f['details']}
        if d.get('original_csv')!=row['original_value'] or Fraction(_decimal(d.get('trade_value')))!=candidate:return False
        if not self.trade_refs(f['source_refs'],originals[0]):return False
        self.sources.bind(dict(row,source_refs=f['source_refs']))
        return True


_VOLUME_KEYS='schema_version policy_sha256 volume_semantics_policy symbol day_start timestamp hour_classification day_applicable original_volume trade_volume volume_delta volume_source tail_group_count tail_count tail_volume tail_first_timestamp tail_last_timestamp prefix_first_timestamp prefix_count source_refs reason_codes confidence_evidence'
_HOUR_CLASSES=('STRICT_C3','TERMINAL_SUFFIX_EXACT','PARTIAL_TIMESTAMP_SUBSET','PARTIAL_SUBSET_UNDETERMINED','NO_COMPLETE_SUFFIX','POSITIVE_VOLUME_DELTA','MISSING_ORIGINAL_HOUR','IDENTITY_UNCERTAIN','OUT_OF_SCOPE','C1_INVALID','C2_CONFLICT','EMPTY_PREFIX')


class _VolumeEvidence(_AdjudicationEvidence):
    """Independently authenticate complete-group suffixes against original bytes."""
    def __init__(self,sources,findings,report_sha,rows,policy_sha,verified,missing_trades,correction_days):
        super().__init__(sources,findings,report_sha)
        self.semantics={};self.valid_hours=set();self.selected_days=set();self.incomplete_days=set();order=[];by_day={}
        for r in rows:
            _keys(r,_VOLUME_KEYS);_symbol(r['symbol'])
            day=_integer(r['day_start']);t=_integer(r['timestamp'])
            if (r['schema_version']!='r8_volume_semantics_v2' or r['volume_semantics_policy']!=V2
                or r['policy_sha256']!=policy_sha or day%DAY or t%HOUR or not day<=t<day+DAY
                or r['hour_classification'] not in _HOUR_CLASSES or type(r['day_applicable']) is not bool):
                raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
            key=(r['symbol'],t)
            if key in self.semantics:raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
            self.semantics[key]=r;order.append((day,r['symbol'],t))
            by_day.setdefault((r['symbol'],day),[]).append(r)
            _refs(r['source_refs'],sources.root,verified,missing_trades)
            if r['reason_codes']!=sorted(set(r['reason_codes'])) or any(not isinstance(x,str) for x in r['reason_codes']):raise InvalidInput('INVALID_REASON_CODES')
            if r['volume_source'] not in (None,'v1_strict','trade_reconstructed_terminal_suffix'):raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
            for name in ('original_volume','trade_volume','volume_delta','tail_volume','tail_first_timestamp','tail_last_timestamp','prefix_first_timestamp'):
                if r[name] is not None and (not isinstance(r[name],str) or not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?',r[name])):raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
            for name in ('tail_count','tail_group_count','prefix_count'):
                if r[name] is not None:_integer(r[name])
            _keys(r['confidence_evidence'],'prefix_hlc tail_minute next_hour_open')
            for e in r['confidence_evidence'].values():
                _keys(e,'status source_refs details')
                if e['status'] not in ('SUPPORTS','CONTRADICTS','UNAVAILABLE','AMBIGUOUS'):raise InvalidInput('INVALID_CONFIDENCE_EVIDENCE')
                _refs(e['source_refs'],sources.root,verified,missing_trades)
                names=[]
                for d in e['details']:
                    _keys(d,'name value')
                    if not isinstance(d['name'],str) or d['value'] is not None and not isinstance(d['value'],str):raise InvalidInput('INVALID_DETAIL')
                    names.append(d['name'])
                if names!=sorted(set(names)):raise InvalidInput('INVALID_DETAIL_ORDER')
            if r['hour_classification'] in ('STRICT_C3','TERMINAL_SUFFIX_EXACT'):
                if any(x['kind']=='trade' and (x['relative_path'] is None or x['relative_path'] in missing_trades) for x in r['source_refs']):
                    self.incomplete_days.add((r['symbol'],day))
                else:
                    if not self.authenticate(r):raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
                    self.valid_hours.add(key)
        if order!=sorted(order):raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
        for symbol,day in correction_days|set(by_day):
            ds=by_day.get((symbol,day),[])
            applicable=all((symbol,r['timestamp']) in self.valid_hours for r in ds) and any(r['hour_classification']=='TERMINAL_SUFFIX_EXACT' for r in ds)
            manifest=sources.load_manifest()
            first=min((m.get('first_timestamp',day) for m in manifest['files'].values() if m.get('symbol')==symbol and m.get('interval')=='60'),default=day)
            delivery=int(manifest.get('universe',{}).get(symbol,{}).get('deliveryTime',0))
            expected=set(range(max(first,day),min(day+DAY,((delivery+HOUR-1)//HOUR)*HOUR) if delivery else day+DAY,HOUR))
            if not expected<={r['timestamp'] for r in ds}:raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
            applicable &= {r['timestamp'] for r in ds}==expected
            # Missing originals remain a per-day evidence gap. Retain the
            # declaration for schema/source identity, never for proof of e.
            if (symbol,day) in self.incomplete_days:applicable=ds[0]['day_applicable']
            if any(r['day_applicable']!=applicable for r in ds):raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
            for r in ds:
                source='trade_reconstructed_terminal_suffix' if applicable and r['hour_classification']=='TERMINAL_SUFFIX_EXACT' else 'v1_strict' if r['hour_classification']=='STRICT_C3' else None
                if r['volume_source']!=source:raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
                if source=='trade_reconstructed_terminal_suffix' and not {'C3_ORIGINAL_FAIL','TERMINAL_SUFFIX_SOURCE_SELECTED','TRADE_SOURCE_SELECTED_BY_E','SOURCE_TRUTH_UNVERIFIED'}<=set(r['reason_codes']):raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
            if applicable:self.selected_days.add((symbol,day))

    def authenticate(self,r):
        symbol=r['symbol'];t=r['timestamp'];day=r['day_start']
        originals=[x for x in r['source_refs'] if x['kind']=='trade' and x['row'] is None and x['relative_path'] is not None]
        if len(originals)!=1:return False
        try:totals=self.trade_totals(originals[0],symbol,day)
        except (OSError,InvalidInput):return False
        if totals is None:return False
        a=totals.get(('60',t),dict(volume=Fraction(0),groups={}))
        original=Fraction(_decimal(r['original_volume']));delta=original-a['volume']
        if Fraction(_decimal(r['trade_volume']))!=a['volume'] or Fraction(_decimal(r['volume_delta']))!=delta:return False
        groups=a['groups'];stamps=sorted(groups);prefix=[];tail=[]
        if delta==0:
            if r['hour_classification']!='STRICT_C3':return False
            prefix=stamps
        elif delta<0:
            # An independent forward prefix equality, not DV1's reverse suffix loop.
            running=Fraction(0)
            for i,stamp in enumerate(stamps[:-1]):
                running+=sum(size for size,_ in groups[stamp])
                if running==original:prefix=stamps[:i+1];tail=stamps[i+1:];break
            if not prefix or r['hour_classification']!='TERMINAL_SUFFIX_EXACT':return False
        else:return False
        expected=dict(tail_group_count=len(tail),tail_count=sum(len(groups[s]) for s in tail),prefix_count=sum(len(groups[s]) for s in prefix))
        if any(r[k]!=v for k,v in expected.items()):return False
        if Fraction(_decimal(r['tail_volume']))!=sum((size for s in tail for size,_ in groups[s]),Fraction(0)):return False
        for name,stamp in (('tail_first_timestamp',tail[0] if tail else None),('tail_last_timestamp',tail[-1] if tail else None),('prefix_first_timestamp',prefix[0] if prefix else None)):
            if (r[name] is not None if stamp is None else r[name] is None or Fraction(_decimal(r[name]))*1000!=stamp):return False
        tail_ids={identity for s in tail for _,identity in groups[s]}
        if not tail_ids<={x['trade_id'] for x in r['source_refs'] if x['kind']=='trade'}:return False
        f=self.findings.get((symbol,'60',t,'volume','C3_QUANTITY'),[])
        if len(f)!=1 or f[0]['reason_code']!=('COVERAGE_RECONCILED' if delta==0 and prefix else 'COVERAGE_CONFLICT'):return False
        d={x['name']:x['value'] for x in f[0]['details']}
        if Fraction(_decimal(d.get('reported_volume')))!=original:return False
        self.sources.bind(dict(symbol=symbol,interval='60',timestamp=t,field='volume',original_value=d['reported_volume'],source_refs=r['source_refs']))
        if d.get('volume_semantics_policy')!=V2 or d.get('hour_classification')!=r['hour_classification']:return False
        if delta!=0 and 'C3_ORIGINAL_FAIL' not in r['reason_codes']:return False
        return True

    def hour_complete(self,symbol,t,original,aggregate):
        r=self.semantics.get((symbol,t))
        if r and r['hour_classification']=='TERMINAL_SUFFIX_EXACT':return (symbol,t//DAY*DAY) in self.selected_days and (symbol,t) in self.valid_hours
        return super().hour_complete(symbol,t,original,aggregate)

    def selected(self,row):
        day=(row['symbol'],row['timestamp']//DAY*DAY)
        return day in self.selected_days and (row['interval']=='D' or self.semantics.get((row['symbol'],row['timestamp']),{}).get('hour_classification')=='TERMINAL_SUFFIX_EXACT')


def _bundle_outcomes(root,p,plan_sha,details=None):
    verification=_json(_path(root,'verification.json').read_bytes())
    if not isinstance(verification,dict):raise InvalidInput('VERIFICATION_BINDING_MISMATCH')
    schema=verification.get('schema_version');v2=schema=='r8_data_verification_v2'
    _keys(verification,_VERIFICATION_KEYS+(' standard_sha256 volume_semantics_policy' if v2 else ''))
    expected_policy=encoded(_policy(p['p3b_manifest_sha256'],V2 if v2 else 'v1-strict'))
    if (schema not in ('r8_data_verification_v1','r8_data_verification_v2') or verification['status'] not in ('READY','BLOCKED')
        or verification['policy_sha256']!=(sha(expected_policy) if v2 else p['policy_sha256']) or verification['p3b_manifest_sha256']!=p['p3b_manifest_sha256']
        or verification['sample_plan_sha256']!=plan_sha or verification['readable']!=p['readable']):
        raise InvalidInput('VERIFICATION_BINDING_MISMATCH')
    if v2 and (verification['volume_semantics_policy']!=V2 or verification['standard_sha256']!=_policy(p['p3b_manifest_sha256'])['standard_sha256']
        or _path(root,'policy.json').read_bytes()!=expected_policy or _path(root,'sample_plan.json').read_bytes()!=encoded(p)):
        raise InvalidInput('POLICY_MISMATCH')
    _keys(verification['counts'],'input_rows checked_days flagged_days corrected_fields unresolved_rows')
    for value in verification['counts'].values():
        _integer(value)
    verified=set();missing_trades=set(); source_rows=_SourceRows(root,p)
    _refs(verification['review_refs'],root,verified)
    if not re.fullmatch('[0-9a-f]{40}',str(verification['tool_commit'])):
        raise InvalidInput('INVALID_TOOL_COMMIT')
    if verification['previous_corrections_sha256'] is not None:
        _hash(verification['previous_corrections_sha256'])
    if not isinstance(verification['reason_codes'],list) or any(not isinstance(x,str) for x in verification['reason_codes']) or verification['reason_codes']!=sorted(set(verification['reason_codes'])):
        raise InvalidInput('INVALID_REASON_CODES')
    if not isinstance(verification['files'],dict) or not {'findings.jsonl','corrections.jsonl'}<=set(verification['files']):
        raise InvalidInput('MISSING_EVIDENCE')
    if v2 and not {'policy.json','volume_semantics.jsonl','sample_plan.json'}<=set(verification['files']):raise InvalidInput('MISSING_EVIDENCE')
    contents={}
    for name,meta in verification['files'].items():
        _keys(meta,'sha256 rows'); _integer(meta['rows'])
        data=_path(root,name).read_bytes()
        if sha(data)!=_hash(meta['sha256']):
            raise InvalidInput('EVIDENCE_HASH_MISMATCH')
        if name in ('findings.jsonl','corrections.jsonl','volume_semantics.jsonl'):
            rows=[_json(line) for line in data.splitlines(keepends=True)]
            if len(rows)!=meta['rows']:
                raise InvalidInput('EVIDENCE_ROW_COUNT_MISMATCH')
            contents[name]=rows
    evidence=_AdjudicationEvidence(source_rows,contents['findings.jsonl'],verification['files']['findings.jsonl']['sha256'])
    if v2:evidence=_VolumeEvidence(source_rows,contents['findings.jsonl'],verification['files']['findings.jsonl']['sha256'],contents['volume_semantics.jsonl'],verification['policy_sha256'],verified,missing_trades,{(r['symbol'],_integer(r['timestamp'])//DAY*DAY) for r in contents['corrections.jsonl']})
    days={}; ids=set(); keys=set(); order=[];reasons={}
    for row in contents['corrections.jsonl']:
        _keys(row,_CORRECTION_KEYS+(' volume_semantics_policy volume_source reason_codes' if v2 else '')); _refs(row['source_refs'],root,verified,missing_trades)
        for name in ('correction_id','unit','formula','reason_code'):
            if not isinstance(row[name],str) or not row[name]:
                raise InvalidInput('INVALID_CORRECTION')
        if not isinstance(row['rule_ids'],list) or any(not isinstance(x,str) or not x for x in row['rule_ids']) or row['rule_ids']!=sorted(set(row['rule_ids'])):
            raise InvalidInput('INVALID_RULE_IDS')
        if row['supersedes'] is not None and (not isinstance(row['supersedes'],str) or not row['supersedes'] or row['supersedes']==row['correction_id']):
            raise InvalidInput('INVALID_SUPERSEDES')
        if row['schema_version']!=('r8_data_correction_v2' if v2 else 'r8_data_correction_v1') or row['policy_sha256']!=verification['policy_sha256'] or row['approval_event']!=('RH-20261022-05' if v2 else 'RH-20261022-04'):
            raise InvalidInput('CORRECTION_BINDING_MISMATCH')
        if v2:
            selected=evidence.selected(row)
            source=('trade_reconstructed_terminal_suffix' if selected else 'v1_strict') if row['field']=='volume' and row['decision']!='UNRESOLVED' else None
            if (row['volume_semantics_policy']!=V2 or row['volume_source']!=source
                or row['reason_codes']!=sorted(set(row['reason_codes']))
                or selected and 'SOURCE_TRUTH_UNVERIFIED' not in row['reason_codes']):raise InvalidInput('VOLUME_SEMANTICS_EVIDENCE_MISMATCH')
            if sha(encoded({k:v for k,v in row.items() if k!='correction_id'}))!=row['correction_id']:raise InvalidInput('CORRECTION_ID_MISMATCH')
        _symbol(row['symbol'])
        t=_integer(row['timestamp']); start,end=_readable(p['readable'])
        if row['interval'] not in ('D','60','1') or row['dataset']!={'D':'kline_day','60':'kline_hour','1':'kline_minute'}[row['interval']] or not start<=t<end or row['field'] not in _FIELDS:
            raise InvalidInput('CORRECTION_SCOPE_MISMATCH')
        if row['decision'] not in ('CORRECT','KEEP','UNRESOLVED') or row['row_action'] not in ('include','missing'):
            raise InvalidInput('INVALID_CORRECTION')
        if row['coverage_status'] not in ('PASS','CONFLICT','UNAVAILABLE','NOT_APPLICABLE') or row['order_status'] not in ('UNIQUE','TIMESTAMP_MULTI_PRICE','UNAVAILABLE','NOT_APPLICABLE'):
            raise InvalidInput('INVALID_CORRECTION_STATUS')
        if row['evidence_kind'] not in ('trade_adjudication','reported_turnover_selection'):
            raise InvalidInput('INVALID_EVIDENCE_KIND')
        l1_only=(row['decision']=='KEEP' and row['reason_code']=='L1_VALID' and row['rule_ids']==['DV-L1']
                 and row['coverage_status']==row['order_status']=='NOT_APPLICABLE')
        needs_l3=row['evidence_kind']=='trade_adjudication' and not l1_only
        if row['decision']!='UNRESOLVED':
            if not any(ref['relative_path'] is not None for ref in row['source_refs']) or row['original_value'] is None:
                raise InvalidInput('MISSING_EVIDENCE')
            if needs_l3 and (
                row['coverage_status']!='PASS' or row['order_status'] not in (('UNIQUE',) if row['field'] in ('open','close') else ('UNIQUE','NOT_APPLICABLE'))
            ):
                raise InvalidInput('INVALID_ADJUDICATION')
            if row['evidence_kind']=='reported_turnover_selection' and row['field']!='turnover':
                raise InvalidInput('INVALID_ADJUDICATION')
        complete=True
        if row['decision']!='UNRESOLVED':
            missing={r['relative_path'] for r in row['source_refs'] if r['kind']=='trade'
                     and (r['relative_path'] is None or r['relative_path'] in missing_trades)}
            source_rows.bind(dict(row,source_refs=[r for r in row['source_refs'] if not (r['kind']=='trade' and r['relative_path'] in missing)]))
            if needs_l3:
                try:complete=not missing and evidence.complete(row)
                except (InvalidInput,KeyError,ValueError) as exc:
                    if isinstance(exc,InvalidInput) and str(exc)!='INVALID_DECIMAL':raise
                    complete=False
                if not complete:reasons.setdefault((row['symbol'],t//DAY*DAY),set()).add('EVIDENCE_INCOMPLETE')
        if (row['decision']=='CORRECT') != (row['corrected_value'] is not None) or (row['decision']=='UNRESOLVED' and row['row_action']!='missing'):
            raise InvalidInput('INVALID_CORRECTION')
        if row['original_value'] is not None and not isinstance(row['original_value'],str):
            raise InvalidInput('INVALID_CORRECTION')
        for name in ('candidate_value','corrected_value'):
            if row[name] is not None:
                _decimal(row[name])
        key=(row['symbol'],row['dataset'],row['interval'],t,row['field'])
        if key in keys or row['correction_id'] in ids:
            raise InvalidInput('DUPLICATE_CORRECTION')
        keys.add(key); ids.add(row['correction_id'])
        order.append((t,row['symbol'],row['dataset'],row['interval'],row['field'],row['correction_id']))
        day=t//DAY*DAY
        state=days.setdefault((row['symbol'],day),dict(error=False,unresolved=False,incomplete=False,semantic=False,covered=set()))
        state['error'] |= row['decision']=='CORRECT' and complete
        state['incomplete'] |= not complete
        state['unresolved'] |= row['decision']=='UNRESOLVED' or row['row_action']=='missing'
        state['semantic'] |= row['decision']=='KEEP' and row['evidence_kind']=='reported_turnover_selection'
        state['covered'].add((row['interval'],t,row['field']))
    if order!=sorted(order):
        raise InvalidInput('INVALID_CORRECTION_ORDER')
    links={r['correction_id']:r['supersedes'] for r in contents['corrections.jsonl']}
    for identity in links:
        visited=set(); current=identity
        while current in links:
            if current in visited:
                raise InvalidInput('CYCLIC_SUPERSEDES')
            visited.add(current); current=links[current]
    finding_order=[]; ids=set()
    for row in contents['findings.jsonl']:
        _keys(row,_FINDING_KEYS); _refs(row['source_refs'],root,verified,missing_trades); _symbol(row['symbol'])
        if row['schema_version']!='r8_data_finding_v1' or row['finding_id'] in ids:
            raise InvalidInput('INVALID_FINDING')
        ids.add(row['finding_id'])
        if row['timestamp'] is not None:
            t=_integer(row['timestamp'])
            if not p['readable']['start']<=t<p['readable']['end']:
                raise InvalidInput('FINDING_SCOPE_MISMATCH')
        names=[]
        for detail in row['details']:
            _keys(detail,'name value')
            if not isinstance(detail['name'],str) or detail['value'] is not None and not isinstance(detail['value'],str):
                raise InvalidInput('INVALID_DETAIL')
            names.append(detail['name'])
        if names!=sorted(set(names)):
            raise InvalidInput('INVALID_DETAIL_ORDER')
        finding_order.append((row['timestamp'] if row['timestamp'] is not None else -1,row['symbol'],row['dataset'],row['interval'],row['field'],row['finding_id']))
    if finding_order!=sorted(finding_order):
        raise InvalidInput('INVALID_FINDING_ORDER')
    result={}
    for (symbol,day),state in days.items():
        required={(interval,t,field) for interval,times in (('D',[day]),('60',range(day,day+DAY,HOUR))) for t in times for field in _FIELDS}
        unresolved=state['unresolved'] or verification['status']=='BLOCKED' or not required<=state['covered']
        result[(symbol,day)]=('e' if state['error'] else 'u' if state['incomplete'] or unresolved else 's' if state['semantic'] else 'ok')
    if details is not None:details.update(policy=V2 if v2 else 'v1-strict',verification=verification,corrections=contents['corrections.jsonl'],findings=contents['findings.jsonl'],semantics=contents.get('volume_semantics.jsonl',[]))
    return result,reasons


def summarize_sample(plan_root, verification_roots, artifact_root):
    """Consume DV1 bundles. Missing/incomplete sampled days always count as u.

    SourceRef paths must resolve to original, hash-matching files within each
    supplied bundle root. The recorder packages opaque originals, the pinned
    P3b manifest/request log and DV3 inventory without rewriting references.
    Completed decisions require actual row SHA, identity, time and original
    value bindings; unavailable or mismatched evidence fails closed.
    Human-readable report keeps statistical diagnostics outside the fixed JSON
    contracts. It never substitutes the expanded denominator for the base one.
    The report's plan SHA and required_prefix lines are also DV1's explicit
    expansion handoff; DV1 validates the bounds and archives these exact bytes.
    """
    try:
        p,plan_sha=_load_plan(plan_root)
        outcomes={};day_reasons={};reasons=[]
        for root in verification_roots:
            bundle_outcomes,bundle_reasons=_bundle_outcomes(root,p,plan_sha)
            day_reasons.update(bundle_reasons)
            for key,value in bundle_outcomes.items():
                if key in outcomes:
                    raise InvalidInput('OVERLAPPING_VERIFICATION')
                outcomes[key]=value
        H=len(p['strata']); total=sum(s['population_size'] for s in p['strata'])
        estimates=[Fraction(0),Fraction(0)]; uppers=[Fraction(0),Fraction(0)]
        lines=['sample_plan_sha256='+plan_sha,'base denominator only; expansion is diagnostic']
        for s in p['strata']:
            N,n=s['population_size'],s['base_size']
            values=[outcomes.get((d['symbol'],d['day_start']),'u') for d in s['draws']]
            base=values[:n]; e,u,semantic=(base.count(x) for x in ('e','u','s'))
            # Only the base and, when triggered, its frozen expansion participate.
            evaluated=s['draws'] if e or u else s['draws'][:n]
            for d in evaluated:reasons.extend(day_reasons.get((d['symbol'],d['day_start']),()))
            lines.append(f"{s['year']} {s['tier']} N={N} n={n} e={e} u={u} s={semantic}")
            for i,x in enumerate((e,e+u)):
                upper=hypergeometric_upper(N,n,x,Fraction(1,20*H))
                solo=hypergeometric_upper(N,n,x,Fraction(1,20))
                estimates[i]+=Fraction(N,total)*Fraction(x,n)
                uppers[i]+=Fraction(N,total)*upper
                lines.append(f'{("error","conservative")[i]} simultaneous_upper={upper.numerator}/{upper.denominator} standalone95={solo.numerator}/{solo.denominator}')
            if e or u:
                lines.append(f"required_prefix={s['max_size']} max_expansions=1")
                if n<s['max_size']:
                    extra=s['draws'][n:]
                    observed=[outcomes.get((d['symbol'],d['day_start'])) for d in extra]
                    if any(x in ('e','u') for x in observed):
                        reasons.append('EXPANSION_FAILED_REFER_CONDUCTOR')
                    elif any(x is None for x in observed):
                        reasons.append('EXPANSION_REQUIRED')
                else:
                    reasons.append('CENSUS_FAILURE_REFER_CONDUCTOR')
        for i,name in enumerate(('error','conservative')):
            for label,value in (('estimate',estimates[i]),('upper',uppers[i])):
                lines.append(f'{name}_{label}={value.numerator}/{value.denominator}')
        if uppers[1]>Fraction(1,40):
            reasons.append('UPPER_LIMIT_EXCEEDED')
        if not verification_roots:
            reasons.append('VERIFICATION_NOT_ARCHIVED')
        lines.append('status='+('BLOCKED' if reasons else 'READY'))
        return _emit(artifact_root,'sample_report.txt', ('\n'.join(lines)+'\n').encode(),len(lines),reasons)
    except (InvalidInput,OSError,EOFError,TypeError,KeyError,IndexError,ValueError) as exc:
        return _handoff(artifact_root,reasons=(str(exc) if isinstance(exc,InvalidInput) else 'INVALID_EVIDENCE',))


def summarize_policies(plan_root,v1_verification_roots,v2_verification_roots,artifact_root):
    """§13.6 five-part comparison of one frozen sample; acceptance stays pending.

    The original single-policy sample reports retain §4.5 and their exact
    expansion handoff grammar. This comparison is recorder evidence, never an
    expansion instruction, a hypothesis input, or an acceptance decision.
    """
    try:
        p,plan_sha=_load_plan(plan_root,allow_empty=True);all_outcomes={};all_rows={};all_semantics={};bundles={}
        for version,roots in (('v1-strict',v1_verification_roots),(V2,v2_verification_roots)):
            outcomes={};rows=[];semantics=[];bundles[version]=[]
            for root in roots:
                detail={};values,_=_bundle_outcomes(root,p,plan_sha,detail)
                if detail['policy']!=version:raise InvalidInput('POLICY_MISMATCH')
                if set(values)&set(outcomes):raise InvalidInput('OVERLAPPING_VERIFICATION')
                outcomes.update(values);rows+=detail['corrections'];semantics+=detail['semantics']
                bundles[version].append((root,detail['verification']))
            all_outcomes[version]=outcomes;all_rows[version]=rows;all_semantics[version]=semantics
        if set(all_outcomes['v1-strict'])!=set(all_outcomes[V2]):raise InvalidInput('FROZEN_SAMPLE_PAIR_MISMATCH')
        lines=['sample_plan_sha256='+plan_sha,
               'base denominator only; expansion is diagnostic' if p['strata'] else
               'batch_kind=purposive sampling=nonrandom upper_bound=NOT_APPLICABLE acceptance=NOT_APPLICABLE',
               'acceptance_target=PENDING_OPERATOR_DECISION']
        reasons=['ACCEPTANCE_TARGET_PENDING'];files={}
        if not p['strata']:
            lines.append('sampling_population=EMPTY_POPULATION');reasons.append('EMPTY_POPULATION')
        for version,roots in (('v1-strict',v1_verification_roots),(V2,v2_verification_roots)):
            if not p['strata']:continue
            folder='v1' if version=='v1-strict' else 'v2'
            report=summarize_sample(plan_root,roots,Path(artifact_root)/folder)
            if report['primary_file'] is None:raise InvalidInput('POLICY_REPORT_UNAVAILABLE')
            reasons+=report['reason_codes']
            for name,meta in report['files'].items():files[folder+'/'+name]=meta
            lines += ['policy='+version,(Path(report['artifact_root'])/report['primary_file']).read_text().rstrip('\n')]
        frozen_base={(d['symbol'],d['day_start']) for s in p['strata'] for d in s['draws'][:s['base_size']]}
        verified_days=set(all_outcomes['v1-strict'])
        full_batch=frozen_base if p['strata'] else verified_days
        groups=[('full_batch',full_batch)]
        for s in p['strata']:
            groups.append((f"base_stratum year={s['year']} tier={s['tier']} N={s['population_size']}",
                {(d['symbol'],d['day_start']) for d in s['draws'][:s['base_size']]}))
        if p['strata'] and verified_days-frozen_base:
            groups.append(('verified_outside_base',verified_days-frozen_base))
        for level,days in groups:
            lines.append(f'level={level} day_denominator={len(days)}')
            if level=='verified_outside_base':
                lines += ['main_denominator=excluded sampling=nonrandom upper_bound=NOT_APPLICABLE acceptance=NOT_APPLICABLE',
                          'verified_days='+encoded(sorted([list(k) for k in days])).decode().strip()]
            for version,suffix in (('v1-strict','v1'),(V2,'policy')):
                values=[all_outcomes[version].get(key,'u') for key in days]
                lines.append(f'n_error_{suffix}={values.count("e")} n_unresolved_{suffix}={values.count("u")} n_semantics_{suffix}={values.count("s")}')
            selected=[r for r in all_semantics[V2] if (r['symbol'],r['day_start']) in days and r['day_applicable'] and r['hour_classification']=='TERMINAL_SUFFIX_EXACT']
            risk={(r['symbol'],r['day_start']) for r in selected}
            union=risk|{k for k in days if all_outcomes[V2].get(k,'u') in ('e','u')}
            lines += [f'n_terminal_source_selected_days={len(risk)} n_terminal_source_selected_hours={len(selected)} n_tail_trades={sum(r["tail_count"] for r in selected)}',
                f'n_source_truth_unverified={len(risk)} day_denominator={len(days)} risk_union_days={len(union)}',
                'original_C3_failed_selected_days='+encoded(sorted([list(k) for k in risk])).decode().strip()]
            tail_keys={(r['symbol'],r['timestamp']) for r in selected}
            for interval in ('D','60'):
                rows=[r for r in all_rows[V2] if r['interval']==interval and (r['symbol'],r['timestamp']//DAY*DAY) in risk
                      and (interval=='D' or (r['symbol'],r['timestamp']) in tail_keys)]
                corrected=[r for r in rows if r['decision']=='CORRECT' and 'TRADE_SOURCE_SELECTED_BY_E' in r['reason_codes']]
                lines.append(f'interval={interval} n_volume_corrected_e={sum(r["field"]=="volume" for r in corrected)} n_price_corrected_e={sum(r["field"] in ("high","low","close") for r in corrected)}')
            for version in ('v1-strict',V2):
                rows=[r for r in all_rows[version] if (r['symbol'],r['timestamp']//DAY*DAY) in days]
                flags={}
                for r in rows:
                    codes=set(r.get('reason_codes',[]))&{'C2_WINDOWS','C2_CONFLICT','TIMESTAMP_MULTI_PRICE','POST_L1_FAILED','POST_CORRECTION_L1_FAIL','POST_L2_UNRESOLVED'}
                    if r['decision']=='UNRESOLVED':codes.add(r['reason_code'])
                    for code in codes:flags.setdefault(code,set()).add((r['symbol'],r['timestamp']//DAY*DAY))
                lines.append('overlapping_unresolved_flags policy='+version+' '+encoded({k:len(v) for k,v in sorted(flags.items())}).decode().strip())
                for interval in ('D','60'):
                    scoped=[r for r in rows if r['interval']==interval];by_row={}
                    for r in scoped:by_row.setdefault((r['symbol'],r['timestamp']),set()).add(r['row_action'])
                    included=sum(actions=={'include'} for actions in by_row.values())
                    lines.append(f'availability policy={version} interval={interval} row_denominator={len(by_row)} include={included} missing={len(by_row)-included}')
                    for field in _FIELDS:
                        values=[r['decision'] for r in scoped if r['field']==field]
                        lines.append(f'field={field} KEEP={values.count("KEEP")} CORRECT={values.count("CORRECT")} UNRESOLVED={values.count("UNRESOLVED")}')
        # Preserve field reasons, overlapping unresolved flags, original and
        # candidate values and their source hashes without reclassifying e as u.
        for version in ('v1-strict',V2):
            for r in all_rows[version]:
                detail={k:r[k] for k in ('symbol','interval','timestamp','field','decision','row_action','original_value','candidate_value','corrected_value','reason_code','source_refs')}
                detail['reason_codes']=r.get('reason_codes',[r['reason_code']])
                lines.append('field_evidence policy='+version+' '+encoded(detail).decode().strip())
        migration_reasons={}
        for r in all_rows[V2]:
            migration_reasons.setdefault((r['symbol'],r['timestamp']//DAY*DAY),set()).update(r['reason_codes'])
        for key in sorted(frozen_base|verified_days):
            lines.append('migration '+encoded(dict(symbol=key[0],day_start=key[1],v1=all_outcomes['v1-strict'].get(key,'u'),v2=all_outcomes[V2].get(key,'u'),reason_codes=sorted(migration_reasons.get(key,())))).decode().strip())
        data=('\n'.join(lines)+'\n').encode()
        return _emit(artifact_root,'sample_report.txt',data,len(data.splitlines()),reasons,files)
    except (InvalidInput,OSError,EOFError,TypeError,KeyError,IndexError,ValueError) as exc:
        return _handoff(artifact_root,reasons=(str(exc) if isinstance(exc,InvalidInput) else 'INVALID_EVIDENCE',))


@dataclass(frozen=True)
class DownloadRequest:
    request_id: str
    symbol: str
    day_start: int
    interval: str
    source_kind: str
    url: str


@dataclass
class Response:
    status: int
    headers: object
    body: object  # Binary file-like; caller always closes it, including HEAD/errors.


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def _transport(method,url):
    # No ambient proxies, cookies, netrc, auth, redirect or caller headers.
    opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context()),_NoRedirect())
    req=Request(url,method=method,headers={'User-Agent':'r8-verification-dv3-v1','Accept-Encoding':'identity'})
    try:
        response=opener.open(req,timeout=30)
    except HTTPError as exc:
        response=exc
    return Response(response.code,response.headers,response)


def _url(request, approved, flagged):
    _symbol(request.symbol); day=_integer(request.day_start)
    if day%DAY:
        raise InvalidInput('INVALID_DAY')
    if not isinstance(request.request_id,str) or not re.fullmatch('[A-Za-z0-9_-]+',request.request_id):
        raise InvalidInput('INVALID_REQUEST_ID')
    if not isinstance(request.url,str) or request.url not in approved:
        raise InvalidInput('URL_NOT_APPROVED')
    u=urlsplit(request.url)
    if (u.scheme!='https' or u.username is not None or u.password is not None or u.port is not None
        or u.fragment or '%' in request.url or '\\' in request.url or any(c.isspace() for c in request.url)
        or u.netloc!=u.hostname):
        raise InvalidInput('INVALID_URL')
    pairs=parse_qsl(u.query,keep_blank_values=True,strict_parsing=True) if u.query else []
    q=dict(pairs)
    if len(q)!=len(pairs):
        raise InvalidInput('DUPLICATE_QUERY')
    date=datetime.fromtimestamp(day//1000,timezone.utc).strftime('%Y-%m-%d')
    symbol=request.symbol
    if request.source_kind=='bybit_trade':
        if request.interval!='trade' or u.hostname!='public.bybit.com' or q or u.path!=f'/trading/{symbol}/{symbol}{date}.csv.gz':
            raise InvalidInput('INVALID_URL')
    elif request.source_kind=='bybit_minute':
        if request.interval!='1' or u.hostname!='api.bybit.com' or u.path!='/v5/market/kline' or set(q)!={'category','symbol','interval','start','end','limit'}:
            raise InvalidInput('INVALID_URL')
        if q['category']!='linear' or q['symbol']!=symbol or q['interval']!='1' or not all(re.fullmatch('[0-9]+',q[k]) for k in ('start','end','limit')):
            raise InvalidInput('INVALID_URL')
        if not day<=int(q['start'])<=int(q['end'])<day+DAY or int(q['start'])%60000 or not 1<=int(q['limit'])<=1000:
            raise InvalidInput('INVALID_URL')
        if (symbol,day) not in flagged:
            raise InvalidInput('MINUTE_REQUIRES_FLAGGED_DAY')
    elif request.source_kind=='binance_hour':
        if request.interval!='60' or u.hostname!='data.binance.vision' or q or u.path!=f'/data/futures/um/daily/klines/{symbol}/1h/{symbol}-1h-{date}.zip':
            raise InvalidInput('INVALID_URL')
    elif request.source_kind=='okx_hour':
        if request.interval!='60' or u.hostname!='www.okx.com' or u.path!='/api/v5/market/history-candles' or set(q)!={'instId','bar','before','after','limit'}:
            raise InvalidInput('INVALID_URL')
        if q['instId']!=symbol[:-4]+'-USDT-SWAP' or q['bar']!='1H' or not all(re.fullmatch('[0-9]+',q[k]) for k in ('before','after','limit')):
            raise InvalidInput('INVALID_URL')
        # OKX bounds are exclusive; only the dispatched UTC day may be returned.
        if int(q['before'])!=day-1 or int(q['after'])!=day+DAY or not 1<=int(q['limit'])<=100:
            raise InvalidInput('INVALID_URL')
    else:
        raise InvalidInput('INVALID_SOURCE_KIND')
    return u.hostname


_RATE_LOCK=threading.Lock()
_RATE_LAST={}
_STOPPED_HOSTS=set()


def _api_status(data,name):
    """Scan top-level JSON spans without decoding any candle value."""
    whitespace=b' \r\n\t'
    def skip(i):
        while i<len(data) and data[i] in whitespace:
            i+=1
        return i
    def string_end(i):
        if data[i]!=34:
            raise InvalidInput('INVALID_API_RESPONSE')
        i+=1
        while i<len(data):
            if data[i]==92:
                i+=2
            elif data[i]==34:
                return i+1
            else:
                i+=1
        raise InvalidInput('INVALID_API_RESPONSE')
    i=skip(0)
    if i>=len(data) or data[i]!=123:
        raise InvalidInput('INVALID_API_RESPONSE')
    i=skip(i+1); found=None; keys=set()
    while i<len(data) and data[i]!=125:
        key_end=string_end(i)
        key=json.loads(data[i:key_end])
        if key in keys:
            raise InvalidInput('INVALID_API_RESPONSE')
        keys.add(key); i=skip(key_end)
        if i>=len(data) or data[i]!=58:
            raise InvalidInput('INVALID_API_RESPONSE')
        i=skip(i+1); begin=i; stack=[]
        while i<len(data):
            c=data[i]
            if c==34:
                i=string_end(i); continue
            if c in (123,91):
                stack.append(c)
            elif c in (125,93):
                if not stack:
                    break
                if stack.pop()!={125:123,93:91}[c]:
                    raise InvalidInput('INVALID_API_RESPONSE')
            elif c==44 and not stack:
                break
            i+=1
        if stack or begin==i:
            raise InvalidInput('INVALID_API_RESPONSE')
        if key==name:
            raw=data[begin:i].strip()
            if not re.fullmatch(rb'(?:[0-9]+|"[0-9]+")',raw):
                raise InvalidInput('INVALID_API_RESPONSE')
            found=json.loads(raw)
        i=skip(i)
        if i<len(data) and data[i]==44:
            i=skip(i+1)
            if i>=len(data) or data[i]==125:
                raise InvalidInput('INVALID_API_RESPONSE')
        else:
            break
    if i>=len(data) or data[i]!=125 or skip(i+1)!=len(data) or found is None:
        raise InvalidInput('INVALID_API_RESPONSE')
    return found


def _limited_send(transport,method,url,host,clock,sleep,stopped):
    if host in stopped:
        raise InvalidInput('HOST_STOPPED')
    # Shared by batches using the same clock, including all HEAD and GET calls.
    # Serial lock also prevents concurrent batches from acquiring a rate slot twice.
    with _RATE_LOCK:
        key=(clock,host)
        now=clock()
        delay=_RATE_LAST.get(key,now-.25)+.25-now
        if delay>0:
            sleep(delay)
        _RATE_LAST[key]=clock()
    response=transport(method,url)
    if type(response.status) is not int:
        response.body.close()
        raise InvalidInput('INVALID_HTTP_STATUS')
    if response.status in (403,429):
        stopped.add(host)
    return response


def _length(headers):
    values=[v for k,v in headers.items() if k.lower()=='content-length']
    if len(values)!=1 or not isinstance(values[0],str) or not re.fullmatch('[0-9]+',values[0]):
        raise InvalidInput('UNKNOWN_LENGTH')
    if any(k.lower() in ('transfer-encoding','content-encoding') and str(v).lower() not in ('','identity') for k,v in headers.items()):
        raise InvalidInput('UNSUPPORTED_ENCODING')
    return int(values[0])


def _utc_ms():
    return time.time_ns()//1_000_000


def fetch_downloads(artifact_root, requests, *, approved_urls, readable,
                    max_total_bytes, max_file_bytes, flagged_days=(), reuse=None,
                    transport=None, clock=time.monotonic, sleep=time.sleep, now=_utc_ms):
    """Finite recorder batch. Preflight every unique URL before the first GET.

    ``reuse`` maps an exact approved URL to (local original path, expected SHA).
    Reuse is opaque and hash checked. Transport injection is for offline tests;
    production uses the fixed verified-TLS/no-auth/no-redirect transport above.
    Budgets are compressed payload bytes, with no hidden retry or pagination.
    """
    rows=[]; reasons=[]; files={}; stopped=_STOPPED_HOSTS if transport is None else set(); responses={}; lengths={}; originals={}
    try:
        start,end=_readable(readable)
        _integer(max_total_bytes); _integer(max_file_bytes)
        if not isinstance(approved_urls,(list,tuple,set,frozenset)) or any(not isinstance(x,str) for x in approved_urls):
            raise InvalidInput('INVALID_APPROVED_LIST')
        approved=set(approved_urls); flagged=set(flagged_days)
        requests=list(requests); send=transport or _transport; reuse=reuse or {}
        if not requests:
            raise InvalidInput('EMPTY_REQUEST_LIST')
        seen=set(); hosts={}; invalid=False
        for request in requests:
            row=dict(schema_version='r8_verification_download_v1',request_id=request.request_id,
                     symbol=request.symbol,day_start=request.day_start,interval=request.interval,
                     source_kind=request.source_kind,url=request.url,started_at=None,finished_at=None,
                     http_status=None,api_status=None,byte_count=None,relative_path=None,sha256=None,
                     status='UNAVAILABLE',reason_code=None)
            rows.append(row)
            try:
                if request.request_id in seen:
                    raise InvalidInput('DUPLICATE_REQUEST_ID')
                seen.add(request.request_id)
                hosts[request.url]=_url(request,approved,flagged)
                if not start<=request.day_start<request.day_start+DAY<=end:
                    row.update(status='SCOPE_INCOMPLETE',reason_code='SCOPE_INCOMPLETE'); invalid=True
            except (InvalidInput,ValueError) as exc:
                row['reason_code']=str(exc) if isinstance(exc,InvalidInput) else 'INVALID_URL'; invalid=True
        rows.sort(key=lambda r:(r['symbol'],r['day_start'],r['source_kind'],r['interval'],r['request_id']))
        if invalid:
            for row in rows:
                if row['reason_code'] is None:
                    row['reason_code']='PREFLIGHT_BLOCKED'
        else:
            # All HEAD responses are closed without reading a body or market values.
            blocked_size=None; preflight_incomplete=False
            for row in rows:
                url=row['url']; host=hosts[url]
                if url in responses:
                    continue
                row['started_at']=_integer(now())
                try:
                    if url in reuse:
                        path,digest=reuse[url]
                        path=Path(path).absolute()
                        if any(p.is_symlink() for p in (path,*path.parents)):
                            raise InvalidInput('UNSAFE_PATH')
                        data=path.read_bytes()
                        if sha(data)!=_hash(digest):
                            raise InvalidInput('REUSE_HASH_MISMATCH')
                        originals[url]=data
                        row['reason_code']='REUSED'
                        lengths[url]=0
                    else:
                        response=_limited_send(send,'HEAD',url,host,clock,sleep,stopped)
                        try:
                            row['http_status']=response.status
                            if response.status!=200:
                                raise InvalidInput('HTTP_UNAVAILABLE')
                            length=_length(response.headers)
                            lengths[url]=length
                            if length>max_file_bytes:
                                raise InvalidInput('SIZE_LIMIT')
                        finally:
                            response.body.close()
                except (InvalidInput,OSError) as exc:
                    reason=str(exc) if isinstance(exc,InvalidInput) else 'TRANSPORT_ERROR'
                    row['reason_code']=reason
                    preflight_incomplete=True
                    if reason in ('UNKNOWN_LENGTH','SIZE_LIMIT','UNSUPPORTED_ENCODING'):
                        blocked_size=reason
                finally:
                    row['finished_at']=_integer(now())
                    responses[url]=row
                if sum(lengths.values())>max_total_bytes:
                    blocked_size='SIZE_LIMIT'
                if blocked_size or preflight_incomplete:
                    break
            if sum(lengths.values())>max_total_bytes:
                blocked_size='SIZE_LIMIT'
            preflight=[f'max_total_bytes={max_total_bytes}',f'max_file_bytes={max_file_bytes}',
                       f'known_download_bytes={sum(lengths.values())}',
                       f'unknown_or_unavailable_urls={len(set(hosts)-set(lengths))}',
                       'storage_bytes_upper_estimate='+str(sum(lengths.values())+sum(len(b) for b in originals.values())),
                       'storage_estimate_excludes_unknown_lengths=true',
                       'elapsed_transfer_time_estimate=UNKNOWN',
                       'minimum_request_spacing_seconds_per_host=0.25']
            for kind in ('bybit_trade','bybit_minute','binance_hour','okx_hour'):
                selected={r['url'] for r in rows if r['source_kind']==kind}
                preflight.append(f'{kind} request_rows={sum(r["source_kind"]==kind for r in rows)} unique_urls={len(selected)} planned_gets={len(selected-set(originals))} known_download_bytes={sum(lengths.get(u,0) for u in selected)}')
            preflight_bytes=('\n'.join(preflight)+'\n').encode()
            _write(artifact_root,'download_preflight.txt',preflight_bytes)
            files['download_preflight.txt']=dict(sha256=sha(preflight_bytes),rows=len(preflight))
            if blocked_size:
                for row in rows:
                    row.update(status='SIZE_BLOCKED',reason_code=blocked_size)
            elif preflight_incomplete or set(hosts)-set(lengths):
                # An HTTP/transport failure has no usable length either. Keep
                # its own failure, and block otherwise successful peers before
                # any GET so the total never silently excludes failed URLs.
                for row in rows:
                    original=responses.get(row['url'],row)
                    if row is not original:
                        identity=row['request_id']; row.update(original); row['request_id']=identity
                    if row['reason_code'] in (None,'REUSED'):
                        if hosts[row['url']] in stopped:
                            row.update(status='UNAVAILABLE',reason_code='HOST_STOPPED')
                        else:
                            row.update(status='SIZE_BLOCKED',reason_code='PREFLIGHT_INCOMPLETE')
            else:
                remaining=max_total_bytes
                batch_stopped=False
                for url,row in responses.items():
                    if batch_stopped:
                        row.update(status='SIZE_BLOCKED',reason_code='PREFLIGHT_BLOCKED')
                        continue
                    if row['reason_code'] not in (None,'REUSED'):
                        continue
                    try:
                        data=originals.get(url)
                        if data is None:
                            response=_limited_send(send,'GET',url,hosts[url],clock,sleep,stopped)
                            try:
                                row['http_status']=response.status
                                if response.status!=200:
                                    raise InvalidInput('HTTP_UNAVAILABLE')
                                length=_length(response.headers)
                                if length!=lengths[url] or length>remaining or length>max_file_bytes:
                                    raise InvalidInput('SIZE_CHANGED')
                                data=response.body.read(length+1)
                                row['byte_count']=len(data)
                                remaining-=len(data)
                                if len(data)!=length:
                                    raise InvalidInput('BODY_LENGTH_MISMATCH')
                            finally:
                                response.body.close()
                        row['byte_count']=len(data)
                        if row['source_kind'] in ('bybit_minute','okx_hour'):
                            # Only status metadata is decoded, never numerical candles.
                            try:
                                status=_api_status(data,'retCode' if row['source_kind']=='bybit_minute' else 'code')
                                row['api_status']=status
                            except (ValueError,KeyError,TypeError):
                                raise InvalidInput('INVALID_API_RESPONSE') from None
                            if status not in (0,'0'):
                                raise InvalidInput('API_UNAVAILABLE')
                        digest=sha(data); name='originals/'+digest+'.bin'
                        if name not in files:
                            _write(artifact_root,name,data)
                            files[name]=dict(sha256=digest,rows=0)
                        row.update(status='AVAILABLE',relative_path=name,sha256=digest)
                    except (InvalidInput,OSError) as exc:
                        reason=str(exc) if isinstance(exc,InvalidInput) else 'TRANSPORT_ERROR'
                        row.update(status='SIZE_BLOCKED' if reason in ('UNKNOWN_LENGTH','SIZE_CHANGED','BODY_LENGTH_MISMATCH') else 'UNAVAILABLE',reason_code=reason)
                        if row['status']=='SIZE_BLOCKED':
                            batch_stopped=True
                    finally:
                        row['finished_at']=_integer(now())
                for row in rows:
                    original=responses[row['url']]
                    if row is not original:
                        request_id=row['request_id']
                        row.update(original); row['request_id']=request_id
        reasons=[row['reason_code'] or 'UNAVAILABLE' for row in rows if row['status']!='AVAILABLE']
        return _emit(artifact_root,'download_inventory.jsonl',b''.join(encoded(row) for row in rows),len(rows),reasons,files)
    except (InvalidInput,OSError,TypeError,ValueError,AttributeError) as exc:
        return _handoff(artifact_root,reasons=(str(exc) if isinstance(exc,InvalidInput) else 'INVALID_DOWNLOAD_INPUT',))
