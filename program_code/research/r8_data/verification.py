"""Offline R8 DV1 (§3–§8.4, RH-20261022-04).

``verify`` is the only handoff entry. Inputs remain immutable; every invocation
writes a new bundle. READY means a reproducible handoff, not research acceptance.
No transport, strategy, ledger mutation, or holdout-opening capability lives here.
C4 is field-specific per conductor clarification of 2026-10-22: only the
earliest/latest timestamp ambiguity blocks O/C; H/L/V ignore within-stamp order.
All source quantities enter through Decimal(string); Fraction arithmetic preserves
exactness independently of the ambient Decimal context. Dataset/time filtering
precedes decoding market fields, including in raw JSON pages crossing the scope.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import urlencode, urlparse, parse_qs
import zipfile

DAY = 86400000
HOUR = 3600000
TRAIN_START = 1577836800000
TRAIN_END = 1751328000000
STANDARD_SHA256 = 'd7c1c884f7f5c3da68fef5889fabf363d589f10cabb90d44e8a264e41de9ca07'
FIELDS = ('open', 'high', 'low', 'close', 'volume', 'turnover')
DELTA = {'D': DAY, '60': HOUR, '1': 60000}
REF_KEYS = set('kind relative_path url sha256 row request_id list_index byte_start byte_end trade_id line_sha256'.split())
INV_KEYS = set('schema_version request_id symbol day_start interval source_kind url started_at finished_at http_status api_status byte_count relative_path sha256 status reason_code'.split())
CORRECTION_KEYS = set('schema_version correction_id symbol dataset interval timestamp field original_value candidate_value corrected_value unit formula evidence_kind source_refs coverage_status order_status rule_ids decision reason_code row_action policy_sha256 approval_event supersedes'.split())


class _Invalid(ValueError):
    """錯誤僅回固定類別，不含來源值或私人路徑。"""


def _fail(code):
    raise _Invalid(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _encoded(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8')


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            _fail('DUPLICATE_JSON_KEY')
        out[k] = v
    return out


def _json(raw):
    try:
        if raw.startswith(b'\xef\xbb\xbf'):
            _fail('INVALID_ENCODING')
        return json.loads(raw, object_pairs_hook=_pairs, parse_float=lambda _: _fail('JSON_FLOAT_DENIED'), parse_constant=lambda _: _fail('INVALID_NUMBER'))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, _Invalid):
            raise
        _fail('INVALID_JSON')


def _keys(obj, expected):
    if not isinstance(obj, dict) or set(obj) != set(expected):
        _fail('SCHEMA_FIELDS')


def _integer(value):
    if type(value) is int:
        return value
    if isinstance(value, (str, bytes)) and re.fullmatch(rb'[0-9]+' if isinstance(value, bytes) else r'[0-9]+', value):
        return int(value)
    _fail('INVALID_TIMESTAMP')


def _number(value):
    if not isinstance(value, str) or not value or value.strip() != value or '_' in value:
        _fail('INVALID_NUMBER')
    try:
        d = Decimal(value)
        if not d.is_finite():
            _fail('INVALID_NUMBER')
        return Fraction(d)
    except (InvalidOperation, ValueError, OverflowError):
        _fail('INVALID_NUMBER')


def _text(value):
    if value is None:
        return None
    value = Fraction(value)
    n, d = value.numerator, value.denominator
    sign = '-' if n < 0 else ''
    n = abs(n)
    a = b = 0
    while d % 2 == 0:
        d //= 2; a += 1
    while d % 5 == 0:
        d //= 5; b += 1
    if d != 1:
        return f'{value.numerator}/{value.denominator}'
    scale = max(a, b)
    digits = str(n * 2**(scale-a) * 5**(scale-b)).zfill(scale+1)
    if not scale:
        return sign+digits
    return sign+(digits[:-scale]+'.'+digits[-scale:]).rstrip('0').rstrip('.')


def _safe(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative or '\x00' in relative:
        _fail('UNSAFE_PATH')
    p = PurePosixPath(relative)
    if p.is_absolute() or any(x in ('', '.', '..') for x in relative.split('/')):
        _fail('UNSAFE_PATH')
    path = root
    for part in p.parts:
        path = path/part
        if path.is_symlink():
            _fail('SYMLINK_DENIED')
    if not path.is_file():
        _fail('SOURCE_UNAVAILABLE')
    return path


def _digest_string(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        _fail('INVALID_SHA256')
    return value


def _source(root, relative, expected):
    _digest_string(expected)
    raw = _safe(root, relative).read_bytes()
    if _sha(raw) != expected:
        _fail('SOURCE_HASH_MISMATCH')
    return raw


def _ref(kind, relative_path=None, sha256=None, **kw):
    r = dict.fromkeys(REF_KEYS)
    r.update(kind=kind, relative_path=relative_path, sha256=sha256, **kw)
    return r


def _refs(refs):
    unique = {_encoded(r): r for r in refs}
    return sorted(unique.values(), key=lambda r:(r['kind'],r['relative_path'] or '',-1 if r['row'] is None else r['row'],-1 if r['list_index'] is None else r['list_index'],-1 if r['byte_start'] is None else r['byte_start'],_encoded(r)))


def _check_ref(ref):
    _keys(ref, REF_KEYS)
    if ref['kind'] not in {'raw','csv','trade','instruments','policy','plan','report'}:
        _fail('SOURCE_REF_KIND')
    if ref['relative_path'] is not None:
        p=ref['relative_path']
        if not isinstance(p,str) or p.startswith('/') or '\\' in p or any(v in ('','.','..') for v in p.split('/')):
            _fail('UNSAFE_PATH')
        _digest_string(ref['sha256'])
    elif ref['sha256'] is not None:
        _fail('SOURCE_REF_IDENTITY')
    for k in ('row','list_index','byte_start','byte_end'):
        v=ref[k]
        if v is not None and (type(v) is not int or v < (1 if k=='row' else 0)):
            _fail('SOURCE_REF_POSITION')
    for k in ('url','request_id','trade_id'):
        if ref[k] is not None and (not isinstance(ref[k],str) or not ref[k]):
            _fail('SOURCE_REF_TYPE')
    if ref['line_sha256'] is not None:
        _digest_string(ref['line_sha256'])


def _policy(manifest_sha):
    return dict(schema_version='r8_data_verification_policy_v1',standard_sha256=STANDARD_SHA256,approval_event='RH-20261022-04',p3b_manifest_sha256=manifest_sha,
                listing=dict(x_pct='50',y_pct='20',z_pct='20',cooling_days=7,quantity='hourly_base_volume_daily_mean',variation='mean_relative_difference',stage_end_ranges=[[1,3],[7,15],[15,30]]),
                sampling=dict(seed=20261022,base_per_stratum=300,max_per_stratum=900,max_expansions=1,confidence='0.95',upper_limit='0.025'),
                turnover=dict(window_days=12,thresholds=['1000000','10000000','100000000'],trigger_pct='5',general='exchange_reported',suspect='sum_hourly_reported'),l4_price_threshold_pct='1')


def _array_spans(raw, key=b'list'):
    """只以詞法定位陣列項目，不解碼範圍外的市場值。"""
    matches=list(re.finditer(rb'"'+key+rb'"\s*:\s*\[',raw))
    if len(matches)!=1:
        _fail('RAW_ARRAY_SCHEMA')
    start=matches[0].end(); pos=start; depth=0; quoted=False; escaped=False; item=None; spans=[]
    while pos<len(raw):
        c=raw[pos]
        if quoted:
            if escaped:escaped=False
            elif c==92:escaped=True
            elif c==34:quoted=False
        elif c==34:quoted=True
        elif c in (91,123):depth+=1
        elif c in (93,125):
            if c==93 and depth==0:
                if item is not None:spans.append((item,pos))
                return spans, raw[:start]+raw[pos:]
            depth-=1
            if depth<0:_fail('RAW_ARRAY_SCHEMA')
        if item is None and c not in (32,9,10,13,44):item=pos
        if not quoted and depth==0 and c==44:
            if item is None:_fail('RAW_ARRAY_SCHEMA')
            spans.append((item,pos));item=None
        pos+=1
    _fail('RAW_ARRAY_SCHEMA')


@dataclass
class _Bar:
    symbol: str
    interval: str
    t: int | None
    values: dict
    refs: list
    nums: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    structural: bool = False
    raw_values: list = field(default_factory=list)

    @property
    def dataset(self):
        return 'kline_day' if self.interval=='D' else 'kline_hour' if self.interval=='60' else 'kline_minute'


class _Run:
    def __init__(self, readable, policy_sha):
        self.start,self.end=readable['start'],readable['end']
        self.policy_sha=policy_sha; self.findings=[]; self.corrections=[]; self.blocked=set(); self.flagged=set(); self.price_days=set(); self.unresolved=set(); self.fids=set()

    def finding(self,symbol,interval,t,field,rule,reason,refs=(),**details):
        # Day diagnostics describe only the readable intersection, not an
        # unreadable midnight row. Preserve the day identity in existing details.
        if rule in ('DV-L2','DV-L4') and t is not None and t%DAY==0 and t<self.start<t+DAY:
            details.update(day_start=t,scope_start=self.start,scope_end=min(t+DAY,self.end))
            t=self.start
        f=dict(schema_version='r8_data_finding_v1',symbol=symbol,dataset='kline_day' if interval=='D' else 'kline_hour' if interval=='60' else 'kline_minute',interval=interval,timestamp=t,field=field,rule_id=rule,reason_code=reason,source_refs=_refs(refs),details=[dict(name=k,value=None if v is None else str(v)) for k,v in sorted(details.items())])
        f['finding_id']=_sha(_encoded(f))
        if f['finding_id'] not in self.fids:self.findings.append(f);self.fids.add(f['finding_id'])

    def mark(self,b,rule,reason,field='row',price=True,**details):
        self.finding(b.symbol,b.interval,b.t,field,rule,reason,b.refs,**details)
        if b.t is not None:
            key=(b.symbol,b.t//DAY*DAY);self.flagged.add(key)
            if price:self.price_days.add(key)

    def l1(self,b):
        if b.t is None:
            b.structural=True;self.blocked.add('INVALID_TIMESTAMP');self.mark(b,'DV-L1','INVALID_TIMESTAMP',field='timestamp');return
        if b.t%DELTA[b.interval]:
            b.structural=True;self.mark(b,'DV-L1','OFF_GRID_TIMESTAMP',field='timestamp')
        for f in FIELDS:
            try:
                n=_number(b.values[f]);b.nums[f]=n
                if f in FIELDS[:4] and n<=0:reason='NONPOSITIVE_PRICE'
                elif f in FIELDS[4:] and n<0:reason='NEGATIVE_QUANTITY'
                else:continue
            except _Invalid:reason='INVALID_NUMBER'
            b.errors.append((f,reason));self.mark(b,'DV-L1',reason,field=f,price=f!='turnover')
        if all(f in b.nums for f in FIELDS[:4]):
            n=b.nums
            if not n['low']<=min(n['open'],n['close'])<=max(n['open'],n['close'])<=n['high']:
                b.errors.append(('row','INVALID_OHLC'));self.mark(b,'DV-L1','INVALID_OHLC')


def _load_p3b(root,manifest,symbols,run):
    request_raw=_source(root,'requests.jsonl',manifest['request_log_sha256'])
    requests={}
    for line in request_raw.splitlines():
        r=_json(line); rid=r['request_id']
        if type(rid) is not int or rid in requests:_fail('REQUEST_ID_CONFLICT')
        requests[rid]=r
    instruments={}
    for rid in manifest['universe_request_ids']:
        r=requests[rid]; raw=_source(root,f'raw/{rid}.json',r['raw_sha256']);page=_json(raw)
        if r['endpoint']!='/v5/market/instruments-info' or r['http_status']!=200 or r['retCode']!=0 or page['retCode']!=0:continue
        for item in page['result']['list']:
            sym=item.get('symbol')
            if sym not in symbols:continue
            if item.get('contractType')!='LinearPerpetual' or item.get('quoteCoin')!='USDT' or item.get('settleCoin')!='USDT':_fail('CONTRACT_IDENTITY')
            if sym in instruments and instruments[sym]!=item:_fail('CONTRACT_IDENTITY')
            instruments[sym]=item
    if set(instruments)!=set(symbols):_fail('CONTRACT_IDENTITY')
    bars=[];meta={}
    for sym in symbols:
        for interval in ('D','60'):
            name=f'kline_{sym}_{interval}.csv.gz'
            if name not in manifest['files']:continue
            m=manifest['files'][name]
            if (m['symbol'],m['dataset'],m['interval'])!=(sym,'kline',interval):_fail('SOURCE_IDENTITY')
            raw=_source(root,name,m['sha256']);meta[(sym,interval)]=m
            selected=[];last=None;by_t={}
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                if stream.readline().strip()!=b'timestamp,open,high,low,close,volume,turnover':_fail('CSV_HEADER')
                for line_no,line in enumerate(stream,2):
                    # 先解碼時間戳；通過可讀範圍檢查後才解碼市場欄位。
                    try:t=_integer(line.split(b',',1)[0])
                    except _Invalid:t=None
                    if t is not None and not run.start<=t<run.end:continue
                    ref=_ref('csv',name,m['sha256'],row=line_no,line_sha256=_sha(line))
                    if t is not None and t+DELTA[interval]>run.end:
                        b=_Bar(sym,interval,t,dict.fromkeys(FIELDS),[ref],structural=True)
                        b.errors.append(('row','SCOPE_INCOMPLETE'));bars.append(b)
                        if t%DELTA[interval]:run.mark(b,'DV-L1','OFF_GRID_TIMESTAMP',field='timestamp')
                        run.mark(b,'DV-L1','SCOPE_INCOMPLETE');continue
                    vals=dict.fromkeys(FIELDS)
                    if t is not None:
                        row=next(csv.reader([line.decode('utf-8')]))
                        if len(row)!=7:_fail('CSV_ROW_SCHEMA')
                        vals=dict(zip(FIELDS,row[1:]))
                    b=_Bar(sym,interval,t,vals,[ref]);run.l1(b);selected.append(b);bars.append(b)
                    if t is not None:
                        if last is not None and t<last:
                            b.structural=True;run.mark(b,'DV-L1','UNSORTED_KEYS')
                        if last is not None and t>last+DELTA[interval]:
                            run.finding(sym,interval,t,'timestamp','DV-L1','MISSING_KEYS',[ref],previous_timestamp=last)
                        last=t;by_t.setdefault(t,[]).append(b)
            for group in by_t.values():
                if len(group)>1:
                    for b in group:b.structural=True;run.mark(b,'DV-L1','DUPLICATE_KEY')
            # 為所選 CSV 列保留 raw 來源；其他時段的頁面只作不透明雜湊。
            raw_by_t={}
            for rid in m.get('source_request_ids',m.get('request_ids',[])):
                r=requests[rid]
                if r['params'].get('symbol')!=sym or r['params'].get('interval')!=interval or r['params'].get('category')!='linear' or r['endpoint']!='/v5/market/kline':_fail('SOURCE_IDENTITY')
                if r['http_status']!=200 or r['retCode']!=0:_fail('RAW_RESPONSE_FAILURE')
                relative=f'raw/{rid}.json';data=_source(root,relative,r['raw_sha256'])
                spans,skeleton=_array_spans(data);header=_json(skeleton)
                if header['retCode']!=0 or header['result'].get('symbol')!=sym or header['result'].get('category')!='linear':_fail('SOURCE_IDENTITY')
                for index,(a,z) in enumerate(spans):
                    prefix=re.match(rb'\s*\[\s*"([0-9]+)"\s*,',data[a:z])
                    if not prefix:continue
                    t=int(prefix[1])
                    if t not in by_t:continue
                    row=_json(data[a:z])
                    if len(row)!=7 or any(not isinstance(v,str) for v in row):_fail('RAW_ROW_SCHEMA')
                    url=r['base_url']+r['endpoint']+'?'+urlencode(sorted(r['params'].items()))
                    ref=_ref('raw',relative,r['raw_sha256'],row=data[:a].count(b'\n')+1,request_id=str(rid),list_index=index,byte_start=a,byte_end=z,url=url,line_sha256=_sha(data[a:z]))
                    raw_by_t.setdefault(t,[]).append((dict(zip(FIELDS,row[1:])),ref))
            for b in selected:
                if b.t is None:continue
                matches=raw_by_t.get(b.t,[])
                if not matches:
                    b.structural=True;run.mark(b,'DV-L1','RAW_SOURCE_MISSING');run.blocked.add('RAW_SOURCE_MISSING')
                if len({_encoded(v) for v,_ in matches})>1:
                    b.structural=True;run.mark(b,'DV-L1','RAW_SOURCE_CONFLICT');run.blocked.add('RAW_SOURCE_CONFLICT')
                for values,ref in matches:
                    b.refs.append(ref);b.raw_values.append(values)
                    for f in FIELDS:
                        if values[f]!=b.values[f]:run.finding(sym,interval,b.t,f,'DV-L1','SOURCE_REPRESENTATION_DIFFERENCE',b.refs,csv_value=b.values[f],raw_value=values[f])
    return bars,meta,instruments


def _load_inventory(path,download_root,symbols,run):
    items=[];seen=set();last=None
    for line in path.read_bytes().splitlines():
        r=_json(line);_keys(r,INV_KEYS)
        if r['schema_version']!='r8_verification_download_v1':_fail('SCHEMA_VERSION')
        if not isinstance(r['request_id'],str) or not r['request_id'] or r['request_id'] in seen:_fail('REQUEST_ID_CONFLICT')
        seen.add(r['request_id'])
        if not isinstance(r['symbol'],str) or not re.fullmatch('[A-Z0-9]+USDT',r['symbol']):_fail('INVENTORY_IDENTITY')
        if type(r['day_start']) is not int or r['day_start']%DAY:_fail('INVENTORY_TIME')
        source=r['source_kind']; interval={'bybit_trade':'trade','bybit_minute':'1','binance_hour':'60','okx_hour':'60'}.get(source)
        if not interval or r['interval']!=interval:_fail('INVENTORY_IDENTITY')
        if r['status'] not in {'AVAILABLE','UNAVAILABLE','SCOPE_INCOMPLETE','SIZE_BLOCKED'}:_fail('INVENTORY_STATUS')
        for k in ('started_at','finished_at','http_status','byte_count'):
            if r[k] is not None and (type(r[k]) is not int or r[k]<0):_fail('INVENTORY_TYPE')
        if r['api_status'] is not None and type(r['api_status']) not in (str,int):_fail('INVENTORY_TYPE')
        if r['reason_code'] is not None and not isinstance(r['reason_code'],str):_fail('INVENTORY_TYPE')
        if not isinstance(r['url'],str) or not r['url']:_fail('INVENTORY_IDENTITY')
        key=(r['symbol'],r['day_start'],source,interval,r['request_id'])
        if last is not None and key<last:_fail('INVENTORY_ORDER')
        last=key
        if r['status']=='AVAILABLE':
            if r['http_status']!=200 or r['sha256'] is None or r['relative_path'] is None or r['byte_count'] is None:_fail('INVENTORY_STATUS')
            _digest_string(r['sha256'])
        elif not r['reason_code']:_fail('INVENTORY_REASON_REQUIRED')
        _check_ref(_inventory_ref(r,'trade' if source=='bybit_trade' else 'raw'))
        if r['symbol'] not in symbols or not run.start<=r['day_start']<run.end:
            continue
        items.append(r)
    return items


def _inventory_ref(r,kind):
    return _ref(kind,r['relative_path'],r['sha256'],url=r['url'],request_id=r['request_id'])


def _payload(r,root):
    raw=_source(root,r['relative_path'],r['sha256'])
    if len(raw)!=r['byte_count']:_fail('BYTE_COUNT_MISMATCH')
    return raw


@dataclass
class _Trades:
    groups: dict = field(default_factory=dict)
    errors: set = field(default_factory=set)
    refs: list = field(default_factory=list)


def _trade_file(r,root,run):
    out=_Trades();out.refs=[_inventory_ref(r,'trade')]
    day=r['day_start'];symbol=r['symbol']
    if not (run.start<=day and day+DAY<=run.end):out.errors.add('SCOPE_INCOMPLETE');return out
    if r['status']!='AVAILABLE':out.errors.add(r['reason_code']);return out
    date=datetime.fromtimestamp(day//1000,timezone.utc).strftime('%Y-%m-%d')
    if r['url']!=f'https://public.bybit.com/trading/{symbol}/{symbol}{date}.csv.gz':out.errors.add('C1_ID_TIME');return out
    raw=_payload(r,root);seen=set();previous=None;directions=set()
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        header=next(csv.reader([stream.readline().decode('utf-8').strip()]))
        if len(set(header))!=len(header) or not {'timestamp','symbol','price','size','trdMatchID','side'}<=set(header):_fail('TRADE_HEADER')
        ti=header.index('timestamp');si=header.index('symbol')
        for rownum,line in enumerate(stream,2):
            row_ref=_ref('trade',r['relative_path'],r['sha256'],url=r['url'],request_id=r['request_id'],row=rownum,line_sha256=_sha(line))
            # 先判斷身份與精確秒數，再解碼價格／數量。
            pieces=line.rstrip(b'\r\n').split(b',')
            if len(pieces)!=len(header):out.errors.add('C1_ID_TIME');out.refs.append(row_ref);continue
            try:
                stamp=_number(pieces[ti].decode('ascii'))*1000
                if pieces[si].decode('ascii')!=symbol or not day<=stamp<day+DAY or not run.start<=stamp<run.end:out.errors.add('C1_ID_TIME');out.refs.append(row_ref);continue
                row=dict(zip(header,next(csv.reader([line.decode('utf-8')]))))
                price,size=_number(row['price']),_number(row['size'])
                if price<=0 or size<=0 or not row['trdMatchID'] or row['trdMatchID'] in seen or row['side'] not in ('Buy','Sell'):out.errors.add('C1_ID_TIME');out.refs.append(row_ref);continue
                seen.add(row['trdMatchID'])
                if previous is not None and previous!=stamp:directions.add(1 if stamp>previous else -1)
                previous=stamp
                ref=_ref('trade',r['relative_path'],r['sha256'],url=r['url'],request_id=r['request_id'],row=rownum,trade_id=row['trdMatchID'],line_sha256=_sha(line))
                group=out.groups.setdefault(stamp,{'prices':set(),'volume':Fraction(0),'turnover':Fraction(0),'refs':[]})
                group['prices'].add(price);group['volume']+=size;group['turnover']+=price*size
                group['refs'].append(ref)
            except (ValueError,UnicodeError):out.errors.add('C1_ID_TIME');out.refs.append(row_ref)
    if len(directions)>1:out.errors.add('C1_ID_TIME')
    return out


def _aggregate(groups):
    if not groups:return None
    stamps=sorted(groups);first,last=groups[stamps[0]],groups[stamps[-1]]
    prices=set().union(*(g['prices'] for g in groups.values()))
    multi=sum(len(g['prices'])>1 for g in groups.values())
    values=dict(open=next(iter(first['prices'])) if len(first['prices'])==1 else None,high=max(prices),low=min(prices),close=next(iter(last['prices'])) if len(last['prices'])==1 else None,volume=sum((g['volume'] for g in groups.values()),Fraction(0)),turnover=sum((g['turnover'] for g in groups.values()),Fraction(0)))
    # 保留原檔及首末／極值見證；全檔原位元組仍由 SHA 綁定。
    refs=first['refs']+last['refs']
    for extremum in (values['high'],values['low']):
        stamp=next(t for t in stamps if extremum in groups[t]['prices']);refs+=groups[stamp]['refs']
    if multi:
        stamp=next(t for t in stamps if len(groups[t]['prices'])>1);refs+=groups[stamp]['refs']
    return values,multi,_refs(refs),stamps[0],stamps[-1],sum(len(g['refs']) for g in groups.values())


def _valid(b):
    return not b.errors and not b.structural


def _l2(run,sym,day,ds,hs,meta,instrument):
    refs=[r for b in ds+hs for r in b.refs]
    # 僅額非法不可製造量缺口，進而錯誤觸發逐筆取數。
    valid=[b for b in hs if not b.structural and not any(f!='turnover' for f,_ in b.errors)]
    times=[b.t for b in hs];flags=[]
    first=meta.get((sym,'60'),{}).get('first_timestamp');delivery=_integer(instrument.get('deliveryTime','0'))
    partial=(first is not None and day<first<day+DAY) or (day<delivery<day+DAY)
    if partial:flags.append('PARTIAL')
    if not (run.start<=day and day+DAY<=run.end):flags.append('SCOPE_INCOMPLETE')
    if not ds or not hs:flags.append('MISSING_COUNTERPART')
    if any(not _valid(b) for b in ds+hs):flags.append('INVALID_INPUT')
    if times and any(t not in set(times) for t in range(min(times),max(times)+HOUR,HOUR)):flags.append('GAPPED')
    if times and not partial and set(times)!=set(range(day,day+DAY,HOUR)):flags.append('GAPPED')
    full=not flags and len(hs)==24 and len(set(times))==24
    if flags:run.flagged.add((sym,day))
    for reason in sorted(set(flags)):
        run.finding(sym,'D',day,'row','DV-L2',reason,refs)
    if not valid:
        run.flagged.add((sym,day))
        run.finding(sym,'D',day,'row','DV-L2','NO_VALID_HOURLY',refs);return
    valid.sort(key=lambda b:b.t)
    agg={'open':valid[0].nums['open'],'high':max(b.nums['high'] for b in valid),'low':min(b.nums['low'] for b in valid),'close':valid[-1].nums['close'],'volume':sum((b.nums['volume'] for b in valid),Fraction(0)),'turnover':sum((b.nums['turnover'] for b in valid),Fraction(0)) if all('turnover' in b.nums and b.nums['turnover']>=0 for b in valid) else None}
    for d in ds:
        for f in FIELDS:
            if f not in d.nums:continue
            if agg[f] is None:
                run.finding(sym,'D',day,f,'DV-L2','TURNOVER_INPUT_INCOMPLETE',refs);continue
            difference=d.nums[f]-agg[f]
            hit=difference!=0
            if not full and f in ('high','low'):hit=difference<0 if f=='high' else difference>0
            if f=='turnover':
                run.finding(sym,'D',day,f,'DV-L2','TURNOVER_DIFFERENCE',refs,difference=_text(difference),hourly_sum=_text(agg[f]));continue
            if f=='volume' or hit:
                run.finding(sym,'D',day,f,'DV-L2','VOLUME_DIFFERENCE' if f=='volume' else 'CROSS_INTERVAL_DIFFERENCE',refs,difference=_text(difference),hourly_value=_text(agg[f]),grid='FULL' if full else ','.join(sorted(set(flags))))
            if hit:run.flagged.add((sym,day));run.price_days.add((sym,day))


def _correction(run,b,f,decision,reason,candidate,refs,coverage,order,rules,formula,kind='trade_adjudication'):
    c=dict(schema_version='r8_data_correction_v1',symbol=b.symbol,dataset=b.dataset,interval=b.interval,timestamp=b.t,field=f,original_value=b.values.get(f),candidate_value=_text(candidate),corrected_value=_text(candidate) if decision=='CORRECT' else None,unit='USDT' if f=='turnover' else 'base_coin' if f=='volume' else 'USDT/base_coin',formula=formula,evidence_kind=kind,source_refs=_refs(b.refs+list(refs)),coverage_status=coverage,order_status=order,rule_ids=sorted(set(rules)),decision=decision,reason_code=reason,row_action='missing' if decision=='UNRESOLVED' else 'include',policy_sha256=run.policy_sha,approval_event='RH-20261022-04',supersedes=None)
    c['correction_id']=_sha(_encoded(c));return c


def _turnover(run,b,hs,meta,suspect):
    refs=[];candidate=None;reason='EXCHANGE_REPORTED';decision='KEEP';formula='exchange_reported'
    if b.interval=='D' and suspect:
        first=meta.get((b.symbol,'60'),{}).get('first_timestamp')
        expected=list(range(b.t,b.t+DAY,HOUR))
        partial=first is not None and b.t<first<b.t+DAY
        # 部分上市日的保存首箱必須確有正成交量。
        if partial:expected=list(range(first,b.t+DAY,HOUR))
        valid=run.start<=b.t and b.t+DAY<=run.end and sorted(h.t for h in hs)==expected
        if partial:valid=valid and any(h.t==first and h.nums.get('volume',0)>0 for h in hs)
        valid=valid and all('turnover' in h.nums and h.nums['turnover']>=0 for h in hs)
        refs=[r for h in hs for r in h.refs]
        if valid:
            candidate=sum((h.nums['turnover'] for h in hs),Fraction(0));formula='sum_hourly_reported';reason='REPORTED_TURNOVER_SELECTION'
            decision='KEEP' if b.nums.get('turnover')==candidate else 'CORRECT'
            run.finding(b.symbol,b.interval,b.t,'turnover','DV-A',reason,b.refs+refs,selected_value=_text(candidate),original_value=b.values['turnover'],difference=_text(candidate-b.nums['turnover']) if 'turnover' in b.nums else None,relative_difference=_text((candidate-b.nums['turnover'])/b.nums['turnover']) if b.nums.get('turnover') else None,hour_keys=','.join(str(h.t) for h in sorted(hs,key=lambda x:x.t)),grid='PARTIAL' if partial else 'FULL',hour_count=len(hs))
        else:decision='UNRESOLVED';reason='TURNOVER_INPUT_INCOMPLETE'
    elif 'turnover' not in b.nums or b.nums['turnover']<0:decision='UNRESOLVED';reason='TURNOVER_INPUT_INCOMPLETE'
    else:candidate=b.nums['turnover']
    return _correction(run,b,'turnover',decision,reason,candidate,refs,'NOT_APPLICABLE','NOT_APPLICABLE',['DV-A'],formula,'reported_turnover_selection')


def _adjudicate(run,sym,day,ds,hs,trades,meta,instrument,minutes=()):
    aggregates={};all_groups=trades.groups
    for interval,rows in [('D',ds),('60',hs)]:
        for b in rows:
            groups={t:g for t,g in all_groups.items() if b.t<=t<b.t+DELTA[interval]}
            aggregates[(interval,b.t)]=_aggregate(groups)
    global_errors=set(trades.errors);hour_errors={h.t:set() for h in hs}
    first=meta.get((sym,'60'),{}).get('first_timestamp',day)
    delivery=_integer(instrument.get('deliveryTime','0'))
    start=max(day,first) if first is not None else day
    end=min(day+DAY,((delivery+HOUR-1)//HOUR)*HOUR) if delivery else day+DAY
    expected=set(range(start,end,HOUR))
    if {h.t for h in hs}!=expected or any(delivery and t>=delivery for t in all_groups):global_errors.add('C2_WINDOWS')
    hmap={}
    for h in hs:hmap.setdefault(h.t,[]).append(h)
    trade_hours={int(t//HOUR)*HOUR for t in all_groups}
    if trade_hours-set(hmap):global_errors.add('C2_WINDOWS')
    for t,rows in hmap.items():
        h=rows[0];agg=aggregates.get(('60',t));errors=hour_errors[t]
        if len(rows)!=1 or h.structural:errors.add('C3_QUANTITY')
        if h.nums.get('volume',0)>0 and not agg:errors.add('C2_WINDOWS')
        if agg and h.nums.get('volume')!=agg[0]['volume']:errors.add('C3_QUANTITY')
        if not agg:errors.add('C5_REBUILD')
        refs=h.refs+trades.refs+(agg[2] if agg else [])
        run.finding(sym,'60',t,'volume','C3_QUANTITY','COVERAGE_CONFLICT' if errors else 'COVERAGE_RECONCILED',refs,reported_volume=h.values['volume'],trade_volume=_text(agg[0]['volume']) if agg else None,trade_count=agg[5] if agg else 0,first_timestamp_ms=_text(agg[3]) if agg else None,last_timestamp_ms=_text(agg[4]) if agg else None)
    for b in ds+hs:
        agg=aggregates.get((b.interval,b.t));errors=set(global_errors)
        if b.interval=='D':errors.update(e for es in hour_errors.values() for e in es)
        else:errors.update(hour_errors.get(b.t,set()))
        if b.structural:errors.add('STRUCTURAL_CONFLICT')
        if not agg:errors.add('C5_REBUILD')
        refs=trades.refs+(agg[2] if agg else [])+[r for h in hs for r in h.refs] if b.interval=='D' else trades.refs+(agg[2] if agg else [])
        for e in sorted(errors):
            rule=e if e in {'C1_ID_TIME','C2_WINDOWS','C3_QUANTITY','C4_ORDER','C5_REBUILD'} else 'DV-L3'
            run.finding(sym,b.interval,b.t,'row',rule,'TIMESTAMP_MULTI_PRICE' if e=='C4_ORDER' else 'COVERAGE_CONFLICT' if e in ('C2_WINDOWS','C3_QUANTITY') else e,b.refs+refs,multi_timestamp_count=agg[1] if agg else None)
        coverage='UNAVAILABLE' if not all_groups else 'CONFLICT' if errors else 'PASS'
        if agg and agg[1]:
            ambiguous=[(t,g) for t,g in sorted(all_groups.items()) if b.t<=t<b.t+DELTA[b.interval] and len(g['prices'])>1]
            sets=[{'timestamp_ms':_text(t),'prices':[_text(v) for v in sorted(g['prices'])]} for t,g in ambiguous]
            run.finding(sym,b.interval,b.t,'row','C4_ORDER','TIMESTAMP_MULTI_PRICE',b.refs+trades.refs,multi_timestamp_count=agg[1],prices=','.join(_text(v) for v in sorted(set().union(*(g['prices'] for _,g in ambiguous)))),timestamp_price_sets=json.dumps(sets,sort_keys=True,separators=(',',':')),open_ambiguous=str(agg[0]['open'] is None).lower(),close_ambiguous=str(agg[0]['close'] is None).lower())
        native={};native_refs=[]
        for label,pool in [('hourly',hs if b.interval=='D' else []),('minute',minutes)]:
            scope=sorted([x for x in pool if b.t<=x.t<b.t+DELTA[b.interval] and _valid(x)],key=lambda x:x.t)
            if scope:
                native_refs.extend(r for x in (scope[0],scope[-1]) for r in x.refs)
                n=[x.nums for x in scope]
                native[label]=dict(open=n[0]['open'],high=max(x['high'] for x in n),low=min(x['low'] for x in n),close=n[-1]['close'],volume=sum(x['volume'] for x in n),turnover=sum(x['turnover'] for x in n))
            else:native[label]={}
        for f in FIELDS:
            run.finding(sym,b.interval,b.t,f,'C5_REBUILD','SOURCE_COMPARISON',b.refs+refs+native_refs,original_csv=b.values[f],original_raw='|'.join(sorted({v[f] for v in b.raw_values})) or None,trade_value=_text(agg[0][f]) if agg else None,hourly_value=_text(native['hourly'].get(f)),minute_value=_text(native['minute'].get(f)))
        row=[]
        for f in FIELDS[:5]:
            candidate=agg[0][f] if agg else None;rule={'open':'DV-O','high':'DV-H','low':'DV-L','close':'DV-C','volume':'DV-V'}[f]
            formula={'open':'earliest_timestamp_unique_price','high':'max(price)','low':'min(price)','close':'latest_timestamp_unique_price','volume':'sum(size)'}[f]
            order=('TIMESTAMP_MULTI_PRICE' if candidate is None else 'UNIQUE') if agg and f in ('open','close') else 'NOT_APPLICABLE' if agg else 'UNAVAILABLE'
            if errors:decision='UNRESOLVED';reason=sorted(errors)[0]
            elif f in ('open','close') and candidate is None:decision='UNRESOLVED';reason='TIMESTAMP_MULTI_PRICE'
            elif f=='open':
                o=b.nums.get('open');lo=b.nums.get('low');hi=b.nums.get('high')
                original_valid=o is not None and o>0 and lo is not None and hi is not None and lo<=o<=hi
                if original_valid:decision='KEEP';reason='EXCHANGE_OPEN_SEMANTICS' if o!=candidate else 'MATCH';rule='DV-O-SEM' if o!=candidate else 'DV-KEEP'
                else:
                    supports=[h for h in (hs if b.interval=='D' else minutes) if b.t<=h.t<b.t+DELTA[b.interval] and _valid(h)]
                    # 原生 open 支持必須來自最早的可用細週期箱。
                    supports=sorted(supports,key=lambda h:h.t)
                    support=bool(supports) and supports[0].nums['open']==candidate
                    if support:decision='CORRECT';reason='TRADE_ADJUDICATION';refs=refs+supports[0].refs
                    else:decision='UNRESOLVED';reason='NATIVE_OPEN_SUPPORT_MISSING'
            else:decision='KEEP' if b.nums.get(f)==candidate else 'CORRECT';reason='MATCH' if decision=='KEEP' else 'TRADE_ADJUDICATION'
            row.append(_correction(run,b,f,decision,reason,candidate,refs,coverage,order,[rule]+sorted(e for e in errors if e.startswith('C') and e[1:2].isdigit())+(['C4_ORDER'] if order=='TIMESTAMP_MULTI_PRICE' else []),formula))
        row.append(_turnover(run,b,hs,meta,True))
        _finish_row(run,b,row)


def _finish_row(run,b,row):
    effective={}
    for c in row:
        if c['decision']!='UNRESOLVED':
            try:effective[c['field']]=_number(c['corrected_value'] if c['decision']=='CORRECT' else c['original_value'])
            except _Invalid:pass
    # 各欄裁決完成後，再對有效整列重跑 L1。
    valid=set(effective)==set(FIELDS)
    if valid:
        n=effective;valid=all(n[f]>0 for f in FIELDS[:4]) and n['low']<=min(n['open'],n['close'])<=max(n['open'],n['close'])<=n['high'] and n['volume']>=0 and n['turnover']>=0
        if not valid:
            for c in row:
                if c['field']!='turnover':c.update(decision='UNRESOLVED',corrected_value=None,reason_code='POST_L1_FAILED')
            run.mark(b,'DV-L1','POST_L1_FAILED')
    missing=not valid or b.structural or any(c['decision']=='UNRESOLVED' for c in row)
    if missing:run.unresolved.add((b.symbol,b.interval,b.t,_encoded(b.refs[0])))
    for c in row:
        c['row_action']='missing' if missing else 'include'
        if b.structural:c.update(decision='UNRESOLVED',corrected_value=None,reason_code='STRUCTURAL_CONFLICT')
        c.pop('correction_id',None);c['correction_id']=_sha(_encoded(c));run.corrections.append(c)


def _minute_rows(r,root,run):
    if r['status']!='AVAILABLE':return []
    if not (run.start<=r['day_start'] and r['day_start']+DAY<=run.end):return []
    u=urlparse(r['url']);q=parse_qs(u.query)
    if u.scheme!='https' or u.hostname!='api.bybit.com' or u.path!='/v5/market/kline' or any(q.get(k)!=[v] for k,v in [('category','linear'),('symbol',r['symbol']),('interval','1')]):_fail('SOURCE_IDENTITY')
    raw=_payload(r,root);spans,skeleton=_array_spans(raw);head=_json(skeleton)
    if head['retCode']!=0 or head['result'].get('symbol')!=r['symbol'] or head['result'].get('category')!='linear':_fail('SOURCE_IDENTITY')
    rows=[]
    for i,(a,z) in enumerate(spans):
        match=re.match(rb'\s*\[\s*"([0-9]+)"\s*,',raw[a:z])
        if not match:_fail('MINUTE_TIMESTAMP')
        t=int(match[1])
        if not (run.start<=t and t+60000<=run.end and r['day_start']<=t<r['day_start']+DAY):continue
        values=_json(raw[a:z])
        if len(values)!=7 or any(not isinstance(x,str) for x in values):_fail('RAW_ROW_SCHEMA')
        ref=_ref('raw',r['relative_path'],r['sha256'],url=r['url'],request_id=r['request_id'],row=raw[:a].count(b'\n')+1,list_index=i,byte_start=a,byte_end=z,line_sha256=_sha(raw[a:z]))
        b=_Bar(r['symbol'],'1',t,dict(zip(FIELDS,values[1:])),[ref]);run.l1(b);rows.append(b)
    return rows


def _external_rows(r,root,run):
    raw=_payload(r,root);out=[]
    if r['source_kind']=='binance_hour':
        u=urlparse(r['url'])
        if u.scheme!='https' or u.hostname!='data.binance.vision' or '/futures/um/' not in u.path or f"/{r['symbol']}/1h/" not in u.path:_fail('EXTERNAL_IDENTITY')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names=archive.namelist()
            if len(names)!=1 or not names[0].endswith('.csv'):_fail('EXTERNAL_ARCHIVE')
            data=archive.read(names[0])
        for n,line in enumerate(data.splitlines(keepends=True),1):
            first=line.split(b',',1)[0]
            if n==1 and first in (b'open_time',b'openTime'):continue
            t=_integer(first)
            if not run.start<=t or t+HOUR>run.end or not r['day_start']<=t<r['day_start']+DAY:continue
            row=next(csv.reader([line.decode('utf-8')]))
            if len(row)!=12:_fail('EXTERNAL_ROW_SCHEMA')
            closed=_integer(row[6])==t+HOUR-1
            out.append((t,row[4],closed,_ref('raw',r['relative_path'],r['sha256'],url=r['url'],request_id=r['request_id'],row=n,line_sha256=_sha(line))))
    else:
        u=urlparse(r['url']);q=parse_qs(u.query);symbol=r['symbol'][:-4]+'-USDT-SWAP'
        if u.scheme!='https' or u.hostname not in ('www.okx.com','app.okx.com') or u.path!='/api/v5/market/history-candles' or q.get('instId')!=[symbol] or q.get('bar')!=['1H']:_fail('EXTERNAL_IDENTITY')
        spans,skeleton=_array_spans(raw,b'data');head=_json(skeleton)
        if str(head.get('code'))!='0':return []
        for i,(a,z) in enumerate(spans):
            match=re.match(rb'\s*\[\s*"([0-9]+)"\s*,',raw[a:z])
            if not match:_fail('EXTERNAL_TIMESTAMP')
            t=int(match[1])
            if not run.start<=t or t+HOUR>run.end or not r['day_start']<=t<r['day_start']+DAY:continue
            row=_json(raw[a:z])
            if len(row)!=9:_fail('EXTERNAL_ROW_SCHEMA')
            out.append((t,row[4],row[8]=='1',_ref('raw',r['relative_path'],r['sha256'],url=r['url'],request_id=r['request_id'],list_index=i,byte_start=a,byte_end=z)))
    return out


def _external_identity(root,refs,venue,symbol,instrument):
    """核對有雜湊的原生合約回應，不信任呼叫者的可比旗標。"""
    for ref in refs:
        _check_ref(ref)
        if ref['kind']!='instruments':continue
        url=urlparse(ref['url'] or '')
        if venue=='binance_hour' and (url.hostname!='fapi.binance.com' or url.path!='/fapi/v1/exchangeInfo'):continue
        if venue=='okx_hour' and (url.hostname not in ('www.okx.com','app.okx.com') or url.path!='/api/v5/public/instruments'):continue
        p=_json(_source(root,ref['relative_path'],ref['sha256']))
        if venue=='binance_hour':
            for item in p.get('symbols',[]):
                if item.get('symbol')!=symbol:continue
                if item.get('contractType')=='PERPETUAL' and item.get('baseAsset')==instrument.get('baseCoin') and item.get('quoteAsset')=='USDT' and item.get('marginAsset')=='USDT':return True,[ref]
        else:
            for item in p.get('data',[]):
                if item.get('instId')!=symbol[:-4]+'-USDT-SWAP':continue
                # OKX vol 為張數，volCcy 為基礎幣；合約乘數必須已知、
                # 為正數，且以相同基礎幣計價。
                try:multiplier=_number(item.get('ctVal'))*_number(item.get('ctMult'))
                except _Invalid:continue
                if item.get('instType')=='SWAP' and item.get('ctType')=='linear' and item.get('settleCcy')=='USDT' and item.get('ctValCcy')==instrument.get('baseCoin') and item.get('uly')==instrument.get('baseCoin')+'-USDT' and multiplier>0:return True,[ref]
    return False,[]


def _l4(run,sym,day,hs,inventory,root,meta,instrument,identity_refs):
    for venue in ('binance_hour','okx_hour'):
        items=inventory.get((sym,day,venue),[])
        available=[r for r in items if r['status']=='AVAILABLE']
        refs=[_inventory_ref(r,'raw') for r in items]
        if not available:
            run.finding(sym,'60',day,'close','DV-L4','UNAVAILABLE',refs,venue=venue,checked_hours=0,expected_hours=len(hs));continue
        identity,irefs=_external_identity(root,identity_refs,venue,sym,instrument)
        if not identity:
            run.finding(sym,'60',day,'close','DV-L4','INCOMPARABLE',refs,venue=venue,checked_hours=0,expected_hours=len(hs));continue
        external={}
        for r in available:
            for t,c,closed,ref in _external_rows(r,root,run):external.setdefault(t,[]).append((c,closed,ref))
        first=meta.get((sym,'60'),{}).get('first_timestamp');delivery=_integer(instrument.get('deliveryTime','0'))
        for h in hs:
            matches=external.get(h.t,[]);reason=None
            if h.t==first or h.t<delivery<h.t+HOUR:reason='INCOMPARABLE_PARTIAL'
            elif not matches:reason='UNAVAILABLE'
            elif len(matches)!=1 or not matches[0][1] or h.t%HOUR:reason='INCOMPARABLE'
            base=h.nums.get('close')
            if base is None or base<=0:reason='UNDEFINED'
            other=None
            if reason is None:
                try:other=_number(matches[0][0])
                except _Invalid:reason='INCOMPARABLE'
                if other is not None and other<=0:reason='INCOMPARABLE'
            if reason is None:
                reason='PRICE_THRESHOLD_EXCEEDED' if abs(other-base)*100>base else 'WITHIN_THRESHOLD'
                if reason=='PRICE_THRESHOLD_EXCEEDED':run.flagged.add((sym,day));run.price_days.add((sym,day))
            run.finding(sym,'60',h.t,'close','DV-L4',reason,h.refs+irefs+[v[2] for v in matches],venue=venue,bybit_close=h.values['close'],external_close=_text(other),volume_availability='BASE_QUANTITY_AVAILABLE' if matches else 'UNAVAILABLE',turnover_availability='USDT_AVAILABLE' if matches else 'UNAVAILABLE')


def _expanded_sample(raw,plan,plan_sha):
    """Consume DV3's existing report; only its declared, frozen prefix is read.

    DV3 owns the trigger and statistics. This validates the handoff bounds and
    identity, never substitutes a draw or changes the base denominator.
    """
    if len(raw)>65536 or not raw.endswith(b'\n') or b'\r' in raw:_fail('EXPANSION_REPORT_SCHEMA')
    lines=raw.decode('utf-8').splitlines()
    if len(lines)<2 or lines[0]!='sample_plan_sha256='+plan_sha:_fail('EXPANSION_PLAN_MISMATCH')
    if lines[1]!='base denominator only; expansion is diagnostic':_fail('EXPANSION_REPORT_SCHEMA')
    i=2;extra=set()
    for s in plan['strata']:
        if i+2>=len(lines):_fail('EXPANSION_REPORT_SCHEMA')
        match=re.fullmatch(r'([0-9]+) (GE_100M|GE_10M|GE_1M|NO_OPEN) N=([0-9]+) n=([0-9]+) e=([0-9]+) u=([0-9]+) s=([0-9]+)',lines[i])
        if match is None:_fail('EXPANSION_REPORT_SCHEMA')
        year,tier,N,n,e,u,semantic=match.groups();N,n,e,u,semantic=map(int,(N,n,e,u,semantic))
        if (int(year),tier,N,n)!=(s['year'],s['tier'],s['population_size'],s['base_size']) or e+u+semantic>n:_fail('EXPANSION_STRATUM_MISMATCH')
        for label in ('error','conservative'):
            i+=1
            if not re.fullmatch(label+r' simultaneous_upper=[0-9]+/[1-9][0-9]* standalone95=[0-9]+/[1-9][0-9]*',lines[i]):_fail('EXPANSION_REPORT_SCHEMA')
        i+=1
        if e or u:
            if i>=len(lines) or lines[i]!=f"required_prefix={s['max_size']} max_expansions=1":_fail('EXPANSION_PREFIX_MISMATCH')
            extra.update((d['symbol'],d['day_start']) for d in s['draws'][n:s['max_size']])
            i+=1
    for label in ('error_estimate','error_upper','conservative_estimate','conservative_upper'):
        if i>=len(lines) or not re.fullmatch(label+r'=[0-9]+/[1-9][0-9]*',lines[i]):_fail('EXPANSION_REPORT_SCHEMA')
        i+=1
    if lines[i:] not in (['status=READY'],['status=BLOCKED']):_fail('EXPANSION_REPORT_SCHEMA')
    if not extra:_fail('EXPANSION_NOT_REQUESTED')
    return extra


def _sample(path,run,manifest_sha,symbols,report=None):
    if path is None:
        if report is not None:_fail('EXPANSION_PLAN_REQUIRED')
        return None,set()
    raw=Path(path).read_bytes();p=_json(raw)
    _keys(p,{'schema_version','policy_sha256','p3b_manifest_sha256','readable','seed','strata'})
    if p['schema_version']!='r8_verification_sample_plan_v1' or p['policy_sha256']!=run.policy_sha or p['p3b_manifest_sha256']!=manifest_sha or p['readable']!={'start':run.start,'end':run.end} or type(p['seed']) is not int or p['seed']!=20261022:_fail('SAMPLE_IDENTITY')
    if not isinstance(p['strata'],list):_fail('SAMPLE_SCHEMA')
    days=set();strata=set();previous=None;tiers=['GE_100M','GE_10M','GE_1M','NO_OPEN']
    for s in p['strata']:
        _keys(s,{'year','tier','population_size','base_size','max_size','draws'})
        if type(s['year']) is not int or s['tier'] not in tiers:_fail('SAMPLE_SCHEMA')
        key=(s['year'],tiers.index(s['tier']))
        if key in strata or previous is not None and key<previous:_fail('SAMPLE_ORDER')
        strata.add(key);previous=key
        for f in ('population_size','base_size','max_size'):
            if type(s[f]) is not int or s[f]<0:_fail('SAMPLE_SCHEMA')
        if s['base_size']!=min(300,s['population_size']) or s['max_size']!=min(900,s['population_size']) or len(s['draws'])!=s['max_size']:_fail('SAMPLE_SCHEMA')
        for rank,d in enumerate(s['draws'],1):
            _keys(d,{'rank','symbol','day_start'})
            if type(d['rank']) is not int or d['rank']!=rank or type(d['day_start']) is not int or d['day_start']%DAY or d['symbol'] not in symbols or not run.start<=d['day_start'] or d['day_start']+DAY>run.end:_fail('SAMPLE_SCOPE')
            if datetime.fromtimestamp(d['day_start']//1000,timezone.utc).year!=s['year']:_fail('SAMPLE_SCHEMA')
            k=(d['symbol'],d['day_start'])
            if k in days:_fail('SAMPLE_DUPLICATE')
            days.add(k)
        # 只處理已選基礎樣本；凍結的後續序列不構成讀取其他日期的授權。
        # 擴樣仍須有 DV3 明確產物。
    base={(d['symbol'],d['day_start']) for s in p['strata'] for d in s['draws'][:s['base_size']]}
    if report is not None:base|=_expanded_sample(report,p,_sha(raw))
    return _sha(raw),base



def _identity_members(raw, wanted):
    """先投影頂層身份欄位，不解碼任何市場值。"""
    pos=0;size=len(raw);out={};seen=set()
    def ws(i):
        while i<size and raw[i] in b' \t\r\n':i+=1
        return i
    def string_end(i):
        i+=1;escape=False
        while i<size:
            c=raw[i]
            if escape:escape=False
            elif c==92:escape=True
            elif c==34:return i+1
            i+=1
        _fail('INVALID_JSON')
    pos=ws(pos)
    if pos>=size or raw[pos]!=123:_fail('INVALID_JSON')
    pos+=1
    while True:
        pos=ws(pos)
        if pos>=size:_fail('INVALID_JSON')
        if raw[pos]==125:return out
        if raw[pos]!=34:_fail('INVALID_JSON')
        end=string_end(pos);key=_json(raw[pos:end]);pos=ws(end)
        if key in seen:_fail('DUPLICATE_JSON_KEY')
        seen.add(key)
        if pos>=size or raw[pos]!=58:_fail('INVALID_JSON')
        pos=ws(pos+1);start=pos;depth=0
        while pos<size:
            c=raw[pos]
            if c==34:pos=string_end(pos);continue
            if c in (91,123):depth+=1
            elif c in (93,125):
                if c==125 and depth==0:break
                depth-=1
            if depth==0 and c==44:break
            pos+=1
        if pos>=size:_fail('INVALID_JSON')
        if key in wanted:out[key]=_json(raw[start:pos])
        if raw[pos]==125:return out
        pos+=1


def _previous(path,run):
    if path is None:return None,{}
    raw=Path(path).read_bytes();by_key={};ids={}
    for line in raw.splitlines():
        identity=_identity_members(line,{'timestamp','symbol','interval','dataset'})
        t=identity.get('timestamp')
        if type(t) is not int or not run.start<=t<run.end or identity.get('symbol') not in run.symbols:_fail('PREVIOUS_SCOPE')
        c=_json(line);_keys(c,CORRECTION_KEYS)
        if c['schema_version']!='r8_data_correction_v1' or c['approval_event']!='RH-20261022-04':_fail('PREVIOUS_CORRECTION_SCHEMA')
        if c['policy_sha256']!=run.policy_sha:_fail('PREVIOUS_POLICY_MISMATCH')
        if c['interval'] not in DELTA or c['dataset']!={'D':'kline_day','60':'kline_hour','1':'kline_minute'}[c['interval']] or c['field'] not in FIELDS:_fail('PREVIOUS_CORRECTION_SCHEMA')
        if c['coverage_status'] not in ('PASS','CONFLICT','UNAVAILABLE','NOT_APPLICABLE') or c['order_status'] not in ('UNIQUE','TIMESTAMP_MULTI_PRICE','UNAVAILABLE','NOT_APPLICABLE'):_fail('PREVIOUS_CORRECTION_SCHEMA')
        if c['evidence_kind'] not in ('trade_adjudication','reported_turnover_selection'):_fail('PREVIOUS_CORRECTION_SCHEMA')
        for name in ('original_value','candidate_value','corrected_value'):
            if c[name] is not None and not isinstance(c[name],str):_fail('PREVIOUS_CORRECTION_SCHEMA')
        for name in ('unit','formula','reason_code'):
            if not isinstance(c[name],str) or not c[name]:_fail('PREVIOUS_CORRECTION_SCHEMA')
        if not isinstance(c['rule_ids'],list) or not c['rule_ids'] or any(not isinstance(x,str) or not x for x in c['rule_ids']) or c['rule_ids']!=sorted(set(c['rule_ids'])):_fail('PREVIOUS_CORRECTION_SCHEMA')
        _digest_string(c['correction_id'])
        if c['supersedes'] is not None:_digest_string(c['supersedes'])
        if c['timestamp'] is None or type(c['timestamp']) is not int or not run.start<=c['timestamp']<run.end:_fail('PREVIOUS_SCOPE')
        for ref in c['source_refs']:_check_ref(ref)
        if not c['source_refs']:_fail('MISSING_EVIDENCE')
        if c['decision'] not in ('KEEP','CORRECT','UNRESOLVED') or c['row_action'] not in ('include','missing'):_fail('PREVIOUS_CORRECTION_SCHEMA')
        if c['decision']=='CORRECT':_number(c['corrected_value'])
        elif c['corrected_value'] is not None:_fail('PREVIOUS_CORRECTION_SCHEMA')
        k=(c['symbol'],c['dataset'],c['interval'],c['timestamp'],c['field'])
        if k in by_key or c['correction_id'] in ids:_fail('CORRECTION_CONFLICT')
        by_key[k]=c;ids[c['correction_id']]=c
    for c in ids.values():
        seen={c['correction_id']};p=c['supersedes']
        while p is not None and p in ids:
            if p in seen:_fail('SUPERSEDES_CYCLE')
            seen.add(p);p=ids[p]['supersedes']
    for c in ids.values():
        if _sha(_encoded({k:v for k,v in c.items() if k!='correction_id'}))!=c['correction_id']:_fail('CORRECTION_ID_MISMATCH')
    return _sha(raw),by_key



def _coalesce_conflicts(corrections):
    """重複來源列一起隔離；同一裁決鍵只輸出一列並保存所有原位置。"""
    groups={}
    for c in corrections:
        k=tuple(c[x] for x in ('symbol','dataset','interval','timestamp','field'))
        # 無法定位的時間不捏造共同市場鍵，仍按原檔／原列定位。
        if c['timestamp'] is None:k+=(_encoded([r for r in c['source_refs'] if r['kind']=='csv']),)
        groups.setdefault(k,[]).append(c)
    result=[]
    for rows in groups.values():
        c=rows[0]
        if len(rows)>1:
            values={r['original_value'] for r in rows}
            c.update(original_value=next(iter(values)) if len(values)==1 else None,candidate_value=None,corrected_value=None,decision='UNRESOLVED',reason_code='DUPLICATE_KEY',row_action='missing',source_refs=_refs([ref for r in rows for ref in r['source_refs']]),rule_ids=sorted(set(['DV-L1']+[rule for r in rows for rule in r['rule_ids']])))
        result.append(c)
    return result


def _bar_index(bars):
    index={}
    for b in bars:
        if b.t is not None:index.setdefault((b.symbol,b.t//DAY*DAY,b.interval),[]).append(b)
    return index


def _inventory_index(inventory):
    index={}
    for r in inventory:index.setdefault((r['symbol'],r['day_start'],r['source_kind']),[]).append(r)
    return index


def _post_l2(run,bars,index):
    """重新檢查有效視圖的跨週期差異，明列語義保留或缺漏。"""
    updates={}
    for c in run.corrections:updates.setdefault((c['symbol'],c['interval'],c['timestamp']),[]).append(c)
    effective={}
    for b in bars:
        if b.t is None:continue
        cs=updates.get((b.symbol,b.interval,b.t),[])
        if any(c['row_action']=='missing' for c in cs):continue
        vals=dict(b.nums)
        for c in cs:
            if c['decision']=='CORRECT':vals[c['field']]=_number(c['corrected_value'])
        if set(vals)==set(FIELDS):effective[(b.symbol,b.interval,b.t)]=(vals,b)
    days={(sym,day) for sym,day,_ in index}
    for sym,day in sorted(days):
        d=effective.get((sym,'D',day));hs=[effective[(sym,'60',t)] for t in range(day,day+DAY,HOUR) if (sym,'60',t) in effective]
        original_hs=index.get((sym,day,'60'),[])
        if not d or not hs or len(hs)!=len(original_hs):
            run.finding(sym,'D',day,'row','DV-L2','POST_L2_MISSING_INPUTS',[r for b in original_hs for r in b.refs]);continue
        full=len(hs)==24
        hn=[h[0] for h in hs];a={'open':hn[0]['open'],'high':max(h['high'] for h in hn),'low':min(h['low'] for h in hn),'close':hn[-1]['close'],'volume':sum(h['volume'] for h in hn)}
        for f in FIELDS[:5]:
            if d[0][f]==a[f]:continue
            if not full and (f=='high' and d[0][f]>=a[f] or f=='low' and d[0][f]<=a[f]):continue
            cs=updates.get((sym,'D',day),[])
            explained=f=='open' and any(c['field']=='open' and c['decision']=='KEEP' and c['reason_code']=='EXCHANGE_OPEN_SEMANTICS' for c in cs)
            run.finding(sym,'D',day,f,'DV-L2','POST_L2_SEMANTICS' if explained else 'POST_L2_UNRESOLVED',d[1].refs,difference=_text(d[0][f]-a[f]))
            if not explained:
                for c in cs:c.update(row_action='missing')
                for c in cs:
                    if c['field']==f:c.update(decision='UNRESOLVED',corrected_value=None,reason_code='POST_L2_UNRESOLVED')
                run.unresolved.add((sym,'D',day,_encoded(d[1].refs[0])))


def _sort_record(r):
    return (-1 if r['timestamp'] is None else r['timestamp'],r['symbol'],r['dataset'],r['interval'],r['field'],r.get('finding_id',r.get('correction_id')))


def verify(*,p3b_root,download_root,inventory_path,output_root,policy_path,readable,symbols,tool_commit=None,sample_plan_path=None,sample_report_path=None,previous_corrections_path=None,review_refs=(),external_contract_refs=()):
    """Create a new §8.4 bundle and return exactly r8_verification_handoff_v1.

    Roots locate independent immutable source namespaces; SourceRef.relative_path
    is relative to its owning source root (P3b for csv/raw P3b, DV3 for downloads,
    the bundle for policy/plan/report). Native external contract responses may be
    supplied as SourceRefs rooted at download_root. Missing identity is explicitly
    INCOMPARABLE. No source is fetched. Only the frozen training range is admitted;
    callers cannot open OOS or holdout through readable or a policy override.
    Optional sample_report_path is DV3's existing sample_report.txt;
    declared expansion prefixes retain the original plan SHA and enter L3.
    """
    out=Path(output_root);files={};primary=None;primary_sha=None;reasons=set();run=None;v=None
    try:
        roots=[Path(p3b_root),Path(download_root)]
        for root in roots+[out,Path(policy_path),Path(inventory_path)]+[Path(p) for p in (sample_plan_path,sample_report_path,previous_corrections_path) if p is not None]:
            if any(p.is_symlink() for p in (root,*root.parents)):_fail('SYMLINK_DENIED')
        roots=[p.resolve() for p in roots]
        if any(out.resolve().is_relative_to(r) or r.is_relative_to(out.resolve()) for r in roots):_fail('OUTPUT_SOURCE_OVERLAP')
        if out.exists():_fail('OUTPUT_EXISTS')
        _keys(readable,{'start','end'})
        if any(type(readable[k]) is not int for k in readable) or not TRAIN_START<=readable['start']<readable['end']<=TRAIN_END:_fail('READABLE_SCOPE_DENIED')
        if not isinstance(symbols,(list,tuple)) or not symbols or len(set(symbols))!=len(symbols) or any(not isinstance(s,str) or not re.fullmatch('[A-Z0-9]+USDT',s) for s in symbols):_fail('SYMBOL_SCOPE')
        symbols=sorted(symbols)
        manifest_raw=_safe(roots[0],'manifest.json').read_bytes();manifest_sha=_sha(manifest_raw);manifest=_json(manifest_raw)
        raw_policy=Path(policy_path).read_bytes();policy=_json(raw_policy)
        if _encoded(policy)!=_encoded(_policy(manifest_sha)) or raw_policy!=_encoded(policy):_fail('POLICY_MISMATCH')
        if manifest.get('tool_version')!='r8-public-data-2':_fail('P3B_VERSION')
        run=_Run(readable,_sha(raw_policy));run.symbols=symbols
        repo=Path(__file__).resolve().parents[3]
        actual_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
        if tool_commit is not None and tool_commit!=actual_commit:_fail('TOOL_COMMIT_MISMATCH')
        tool_commit=actual_commit
        if not re.fullmatch('[0-9a-f]{40}',tool_commit):_fail('TOOL_COMMIT')
        for ref in review_refs:_check_ref(ref)
        if not review_refs:reasons.add('REVIEW_PENDING')
        bars,meta,instruments=_load_p3b(roots[0],manifest,symbols,run)
        inventory=_load_inventory(Path(inventory_path),roots[1],symbols,run)
        bar_index=_bar_index(bars);inventory_index=_inventory_index(inventory)
        sample_report=Path(sample_report_path).read_bytes() if sample_report_path is not None else None
        sample_sha,sample_days=_sample(sample_plan_path,run,manifest_sha,symbols,sample_report)
        previous_sha,previous=_previous(previous_corrections_path,run)
        days={(sym,day) for sym,day,_ in bar_index}|sample_days
        # 已保存的逐筆請求也保留對應日；不因 CSV 缺失而消失。
        # 是否需要裁決，仍依 L1/L2/L4 與固定抽樣集合判斷。
        days|={(sym,day) for sym,day,kind in inventory_index if kind=='bybit_trade'}
        for sym,day in sorted(days):
            ds=bar_index.get((sym,day,'D'),[])
            hs=bar_index.get((sym,day,'60'),[])
            _l2(run,sym,day,ds,hs,meta,instruments[sym])
            _l4(run,sym,day,hs,inventory_index,roots[1],meta,instruments[sym],external_contract_refs)
            items=inventory_index.get((sym,day,'bybit_trade'),[])
            if (sym,day) in sample_days:run.flagged.add((sym,day));run.price_days.add((sym,day))
            minutes=[]
            if (sym,day) in run.price_days:
                for r in inventory_index.get((sym,day,'bybit_minute'),[]):minutes+=_minute_rows(r,roots[1],run)
                mt={}
                for m in minutes:mt.setdefault(m.t,[]).append(m)
                for group in mt.values():
                    if len(group)>1:
                        for m in group:m.structural=True;run.mark(m,'DV-L1','DUPLICATE_KEY')
                if not (run.start<=day and day+DAY<=run.end):trades=_Trades(errors={'SCOPE_INCOMPLETE'})
                elif not items:
                    date=datetime.fromtimestamp(day//1000,timezone.utc).strftime('%Y-%m-%d')
                    trades=_Trades(errors={'TRADE_UNAVAILABLE'},refs=[_ref('trade',url=f'https://public.bybit.com/trading/{sym}/{sym}{date}.csv.gz')])
                else:
                    candidates=[_trade_file(r,roots[1],run) for r in items]
                    # 同一原件可重用；不同原件的衝突不得默選。
                    digests={r['sha256'] for r in items if r['status']=='AVAILABLE'}
                    trades=next((c for r,c in zip(items,candidates) if r['status']=='AVAILABLE'),candidates[0])
                    if len(digests)>1:trades.errors.add('C1_ID_TIME')
                if not ds and not hs:
                    run.finding(sym,'D',day,'row','DV-L3','MISSING_COUNTERPART',trades.refs);run.blocked.add('MISSING_COUNTERPART')
                _adjudicate(run,sym,day,ds,hs,trades,meta,instruments[sym],minutes)
            elif (sym,day) in run.flagged:
                for b in ds+hs:
                    row=[_correction(run,b,f,'KEEP','L1_VALID',b.nums.get(f),[],'NOT_APPLICABLE','NOT_APPLICABLE',['DV-L1'],'original_value') for f in FIELDS[:5]]
                    row.append(_turnover(run,b,hs,meta,True));_finish_row(run,b,row)
        for b in bars:
            if b.t is None:
                cs=[_correction(run,b,f,'UNRESOLVED','INVALID_TIMESTAMP',None,[],'UNAVAILABLE','UNAVAILABLE',['DV-L1'],'unavailable') for f in FIELDS]
                _finish_row(run,b,cs)
        _post_l2(run,bars,bar_index)
        run.corrections=_coalesce_conflicts(run.corrections)
        run.findings.sort(key=_sort_record)
        coverage_sha=_sha(b''.join(_encoded(f) for f in run.findings))
        for c in run.corrections:
            if c['evidence_kind']=='trade_adjudication':c['source_refs']=_refs(c['source_refs']+[_ref('report','findings.jsonl',coverage_sha)])
            key=(c['symbol'],c['dataset'],c['interval'],c['timestamp'],c['field'])
            if key in previous:
                prior=previous[key]
                if c['original_value']!=prior['original_value'] or {r['sha256'] for r in c['source_refs'] if r['kind']=='csv'}!={r['sha256'] for r in prior['source_refs'] if r['kind']=='csv'}:_fail('PREVIOUS_SOURCE_MISMATCH')
                c['supersedes']=prior['correction_id']
            c.pop('correction_id',None);c['correction_id']=_sha(_encoded(c))
        run.findings.sort(key=_sort_record);run.corrections.sort(key=_sort_record)
        reasons|=run.blocked
        if run.unresolved:reasons.add('UNRESOLVED_ROWS_AS_MISSING')
        if any(f['rule_id']=='DV-L4' and f['reason_code'] in ('UNAVAILABLE','INCOMPARABLE','INCOMPARABLE_PARTIAL') for f in run.findings):reasons.add('EXTERNAL_COVERAGE_LIMITED')
        out.mkdir(parents=True)
        payloads={'policy.json':raw_policy,'findings.jsonl':b''.join(_encoded(f) for f in run.findings),'corrections.jsonl':b''.join(_encoded(c) for c in run.corrections)}
        if sample_plan_path is not None:payloads['sample_plan.json']=Path(sample_plan_path).read_bytes()
        if sample_report is not None:payloads['sample_report.txt']=sample_report
        for name,data in payloads.items():
            (out/name).write_bytes(data);files[name]={'sha256':_sha(data),'rows':len(data.splitlines())}
        v=dict(schema_version='r8_data_verification_v1',status='BLOCKED' if run.blocked else 'READY',policy_sha256=run.policy_sha,p3b_manifest_sha256=manifest_sha,sample_plan_sha256=sample_sha,previous_corrections_sha256=previous_sha,review_refs=_refs(review_refs),tool_commit=tool_commit,readable=dict(readable),counts=dict(input_rows=len(bars),checked_days=len(days),flagged_days=len(run.flagged),corrected_fields=sum(c['decision']=='CORRECT' for c in run.corrections),unresolved_rows=len(run.unresolved)),files=dict(files),reason_codes=sorted(reasons))
        data=_encoded(v);(out/'verification.json').write_bytes(data);files['verification.json']={'sha256':_sha(data),'rows':1};primary='verification.json';primary_sha=_sha(data)
    except (_Invalid,OSError,ValueError,KeyError,TypeError,IndexError,OverflowError,zipfile.BadZipFile,EOFError,subprocess.SubprocessError) as exc:
        reasons.add(str(exc) if isinstance(exc,_Invalid) else 'INPUT_OR_TOOL_ERROR')
        # 不輸出可能包含市場值的原始例外文字。
        # 主產物未生成時，依固定契約回傳 null。
        return dict(schema_version='r8_verification_handoff_v1',status='BLOCKED',artifact_root=str(output_root),primary_file=primary,primary_sha256=primary_sha,files=files,reason_codes=sorted(reasons))
    return dict(schema_version='r8_verification_handoff_v1',status=v['status'],artifact_root=str(output_root),primary_file=primary,primary_sha256=primary_sha,files=files,reason_codes=sorted(reasons))
