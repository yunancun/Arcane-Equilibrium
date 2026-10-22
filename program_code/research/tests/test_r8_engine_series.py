"""U6：只使用構造資料，驗收值來自 P4 增補的固定案例。"""

import ast
import copy
import csv
import hashlib
import io
import json
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# 受控擷取移除 cwd 時仍以目前受審版本作絕對匯入。
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from program_code.research.r8_engine import series
from program_code.research.r8_ledger import ledger as ledger_module
from program_code.research.r8_ledger.ledger import canonical


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("離線測試禁止 socket 連線")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def test_g1_target_quantity_fill_and_fee():
    quantity = series.target_quantity("100000", "0.5", "99.50", "0.1")
    assert series.decimal_text(quantity) == "502.5"
    price, fee = series.fill_cost(quantity, "100", "10", "0.00055")
    assert series.decimal_text(price) == "100.1"
    assert series.decimal_text(fee) == "27.6651375"


def test_g2_closing_sell():
    price, fee = series.fill_cost("-502.5", "101", "10", "0.00055")
    assert series.decimal_text(price) == "100.899"
    assert series.decimal_text(fee) == "27.885961125"


@pytest.mark.parametrize(
    "before,after,price,rate,expected",
    [
        pytest.param("502.5", "0", "101", "0.0001", "-5.176755", id="G3"),
        pytest.param("-502.5", "-502.5", "101", "0.0001", "4.973745", id="G4"),
        pytest.param("0", "502.5", "101", "0.0001", "-5.176755", id="G5"),
        pytest.param("502.5", "0", "1", "0.02", "-10.251", id="G6-positive"),
        pytest.param("502.5", "0", "1", "-0.02", "0", id="G6-negative"),
    ],
)
def test_g3_g6_funding_uses_adverse_position(before, after, price, rate, expected):
    amount = series.funding_amount(before, after, price, rate, "0.02")
    assert series.decimal_text(amount) == expected


def test_g7_delisting_uses_adverse_extreme():
    price, fee = series.delisting_cost(
        "502.5", {"low": "0.95", "high": "1.02"},
        {"low": "0.97", "high": "1.04"}, "60", "0.00055",
    )
    assert series.decimal_text(price) == "0.9443"
    assert series.decimal_text(fee) == "0.2609809125"


def cost_parameters():
    return {
        "taker_fee_rate": "0.00055", "stress_fee_rate": "0.00075",
        "slippage_tiers_bps": [
            {"min_turnover": "100000000", "bps": "5"},
            {"min_turnover": "10000000", "bps": "10"},
            {"min_turnover": "1000000", "bps": "20"},
        ],
        "untradeable_below_turnover": "1000000",
        "order_cap_fraction": "0.01",
        "forced_reduce_penalty_bps": "60",
        "slippage_multiplier": "1", "funding_delta": "0.02",
        "funding_blank_min_rate": "0.0001", "liquidity_window_days": 12,
    }


def test_g8_reversal_keeps_reducing_leg_when_increase_is_voided():
    legs = series.order_segments(
        "100", "-50", "100", "0.1", "5", "500000", "10000000",
        True, cost_parameters(),
    )
    assert legs == [
        {"quantity": "-100", "slippage_bps": "60",
         "kind": "forced_reduce_penalty"},
        {"quantity": "-50", "reason": "untradeable"},
    ]


@pytest.mark.parametrize("value", [0.5, float("nan"), True, "NaN", "Infinity", "bad"])
def test_rejects_float_and_nonfinite_inputs(value):
    with pytest.raises(series.SeriesError):
        series.decimal_value(value)


def test_negative_target_rounds_toward_zero():
    assert series.decimal_text(
        series.target_quantity("100000", "-0.5", "99.50", "0.1")
    ) == "-502.5"


@pytest.mark.parametrize(
    "position,target,minimum,notional,daily,hourly,history,expected",
    [
        ("100", "99.95", "0.1", "0", "100000000", "10000000", True, "min_qty"),
        ("100", "99.9", "0.1", "11", "100000000", "10000000", True, "min_notional"),
        ("0", "100", "0.1", "0", "100000000", "999999", True, "order_cap"),
        ("0", "1", "0.1", "0", "100000000", "10000000", False, "insufficient_history"),
    ],
)
def test_void_reasons(position, target, minimum, notional, daily, hourly,
                      history, expected):
    legs = series.order_segments(
        position, target, "100", minimum, notional, daily, hourly,
        history, cost_parameters(),
    )
    assert len(legs) == 1
    assert legs[0]["reason"] == expected


def test_full_close_bypasses_minima_and_stresses_penalty():
    cost = {**cost_parameters(), "slippage_multiplier": "3"}
    assert series.order_segments(
        "0.05", "0", "100", "0.1", "100", "0", "0", False, cost,
    ) == [{"quantity": "-0.05", "slippage_bps": "180",
           "kind": "forced_reduce_penalty"}]


def test_estimated_funding_is_adverse_for_short():
    assert series.decimal_text(
        series.funding_amount("-100", "-50", "10", "0.0001", "0.02",
                              estimated=True)
    ) == "-0.102"


def test_short_delisting_uses_high_and_buy_slippage():
    price, fee = series.delisting_cost(
        "-100", {"low": "0.95", "high": "1.02"},
        {"low": "0.97", "high": "1.04"}, "60", "0.00055",
    )
    assert series.decimal_text(price) == "1.04624"
    assert series.decimal_text(fee) == "0.0575432"


def test_host_imports_are_standard_library_or_approved_packages():
    tree = ast.parse(Path(series.__file__).read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            modules.append(node.module)
            modules.extend(node.module+'.'+alias.name for alias in node.names)
    allowed = ("program_code.research.r8_engine", "program_code.research.r8_ledger")
    for module in modules:
        assert module.split(".")[0] in sys.stdlib_module_names or any(
            module == prefix or module.startswith(prefix + ".") for prefix in allowed
        )
        assert not (module.endswith(".rules") or module.endswith(".materialize"))


# 以下 fixture 完全構造；不讀取任何 U1 真實輸出。
HOUR = 3600000
DAY = 24 * HOUR
START = 1641427200000  # 2022-01-06 星期四 UTC


def historical_materialization(path):
    # 舊 P4 合成回歸明示歷史讀取；run 另綁固定基線的真實 U6 來源 SHA。
    return series.Materialization(path, historical=True)


def write_materialization(tmp_path, *, hours=4, symbols=('BTCUSDT',), hourly=None,
                          daily=None, funding=None, gaps=None, delistings=None):
    root = tmp_path / 'materialized'
    root.mkdir()
    (root / 'source').mkdir()
    manifest = {
        'schema_version': 'r8_materialization_v1', 'u1_manifest_sha256': 'a'*64,
        'u1_tool_version': 'r8-public-data-2', 'ledger_id': 'test-ledger',
        'hypothesis_id': 'h1', 'generation': 1, 'purpose': 'validation',
        'window': {'start': START, 'end': START+hours*HOUR},
        'warmup': {'start': START-13*DAY, 'end': START}, 'readable': {},
        'symbols': list(symbols), 'strategy_symbols': list(symbols), 'files': {},
        'gaps': gaps or {}, 'first_bar': {s: START-13*DAY for s in symbols},
        'min_notional': {s: '0' for s in symbols},
        'funding_interval_ms': {s: 8*HOUR for s in symbols},
        'delistings': delistings or {}, 'limitations': [],
    }
    def write(name, header, rows):
        buf = io.StringIO(newline=''); writer = csv.writer(buf)
        writer.writerow(header); writer.writerows(rows); raw = buf.getvalue().encode()
        (root / 'source' / name).write_bytes(raw)
        manifest['files']['source/'+name] = {
            'sha256': hashlib.sha256(raw).hexdigest(), 'rows': len(rows),
            'first': rows[0][0] if rows else None, 'last': rows[-1][0] if rows else None,
            'source_file': name+'.gz', 'source_sha256': 'b'*64,
        }
    for symbol in symbols:
        bars = (hourly or {}).get(symbol)
        if bars is None:
            bars = [[t, '100', '100', '100', '100', '10000', '10000000']
                    for t in range(START-13*DAY, START+hours*HOUR, HOUR)]
        days = (daily or {}).get(symbol)
        if days is None:
            days = [[t, '100', '100', '100', '100', '1000000', '20000000']
                    for t in range(START-13*DAY, START, DAY)]
        funds = (funding or {}).get(symbol)
        if funds is None:
            funds = [[t, '0'] for t in range(START-13*DAY, START+hours*HOUR+1, 8*HOUR)]
        write('kline_'+symbol+'_60.csv', ['timestamp','open','high','low','close','volume','turnover'], bars)
        write('kline_'+symbol+'_D.csv', ['timestamp','open','high','low','close','volume','turnover'], days)
        write('funding_'+symbol+'_funding.csv', ['timestamp','funding_rate'], funds)
        write('open_interest_'+symbol+'_4h.csv', ['timestamp','open_interest'], [])
    overlay=''.join('bybit,'+s+',cryptofuture,'+s+',USDT,1,0.01,0.1,'+s+',0.1,\n' for s in symbols).encode()
    (root/'symbol_properties_overlay.csv').write_bytes(overlay)
    manifest['symbol_properties_overlay_sha256']=hashlib.sha256(overlay).hexdigest()
    path=root/'materialization.json';path.write_bytes(canonical(manifest))
    return path


def test_materialization_reads_only_source_slices_and_checks_hashes(tmp_path):
    path = write_materialization(tmp_path)
    data = historical_materialization(path)
    assert data.hourly['BTCUSDT'][START]['close'] == Decimal('100')
    assert data.properties['BTCUSDT']['qty_step'] == Decimal('0.1')
    source = path.parent/'source/kline_BTCUSDT_60.csv'
    source.write_bytes(source.read_bytes().replace(b'100,100', b'101,100', 1))
    with pytest.raises(series.SeriesError, match='SHA'):
        historical_materialization(path)


def test_materialization_overlay_hash_and_path_escape(tmp_path):
    path = write_materialization(tmp_path)
    overlay = path.parent/'symbol_properties_overlay.csv'
    overlay.write_bytes(overlay.read_bytes()+b'\n')
    with pytest.raises(series.SeriesError, match='SHA'):
        historical_materialization(path)
    manifest=json.loads(path.read_bytes());manifest['files']['source/../../outside'] = {}
    path.write_bytes(canonical(manifest))
    with pytest.raises(series.SeriesError):
        historical_materialization(path)


def test_funding_schedule_interior_and_unaligned_edges():
    rows={-8*HOUR: Decimal('0.001'), 0: Decimal('0.002'),
          8*HOUR: Decimal('-0.003'), 12*HOUR: Decimal('0.001')}
    events=series.funding_schedule(rows, -9*HOUR, 20*HOUR, 8*HOUR, '0.0001')
    estimates={r['t']:r['rate'] for r in events if r['estimated']}
    assert estimates == {4*HOUR:'0.003', 16*HOUR:'0.001', 20*HOUR:'0.001'}
    assert series.funding_schedule({}, 1, 16*HOUR, 8*HOUR, '0.0001') == [
        {'t':8*HOUR,'rate':'0.0001','estimated':True},
        {'t':16*HOUR,'rate':'0.0001','estimated':True}]


def test_futures_account_does_not_add_notional_to_equity():
    account=series.Account('1000')
    account.fill('X', Decimal('2'), Decimal('100'), Decimal('1'))
    assert account.cash == Decimal('999')
    assert account.equity({'X':Decimal('110')}) == Decimal('1019')
    account.fill('X', Decimal('-3'), Decimal('110'), Decimal('2'))
    assert account.cash == Decimal('1017')
    assert account.positions == {'X':Decimal('-1')}
    assert account.equity({'X':Decimal('105')}) == Decimal('1022')


@pytest.mark.parametrize('scores,selected', [(['-1','100','-1','-1'],None),
    (['100','-1','-1'],None), (['1','1','1'],0), (['1','2','3'],2)])
def test_grid_selection_qualified_majority_and_ties(scores,selected):
    grid=[{'x':i} for i in range(len(scores))]
    neighborhood={'numeric':{'x':list(range(len(scores)))},'categorical':[]}
    result=series.select_grid_point(grid,neighborhood,scores)
    assert result['selected']==selected
    assert result['no_trade']==(selected is None)


def run_for(path, *, decisions=None, windows=None):
    m=json.loads(path.read_bytes())
    cfg={'trial_id':None,'materialization_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'code_commit':'c'*40,'engine_commit':'c'*40,'symbols':m['strategy_symbols'],
         'initial_cash':'100000','leverage':'10','gross_exposure_cap':'1',
         'decision_resolution':'hour','sharpe_frequency_seconds':3600,
         'warmup':m['warmup'],'score_windows':windows or [m['window']], 'folds':[],
         'cost':cost_parameters(),'model_artifact':None,'random_seed':1,
         'strategy':{},'algorithm':{'path':'program_code/research/r8_engine/lean_algo/examples/fixed_schedule.py','class':'FixedSchedule'},
         'mode':'validation'}
    fits=[]
    if windows and windows != [m['window']]:
        cfg['folds']=[{'fit_window':m['warmup'],'score_window':w} for w in windows]
        cfg['strategy']={'grid':[{'x':'1'}],'neighborhood':{'numeric':{'x':['1']},'categorical':[]}}
        fits=[{'fold':i,'fit_window':m['warmup'],'params':{'x':'1'},'model_sha256':'f'*64,
               'selection':{'grid_scores':['1'],'neighborhood_means':['1'],
                            'qualified':[True],'selected':0,'selected_minus_neighborhood':'0','no_trade':False}}
              for i in range(len(windows))]
    return {'schema_version':'r8_lean_run_v1','materialization_sha256':cfg['materialization_sha256'],
            'run_config_sha256':hashlib.sha256(canonical(cfg)).hexdigest(),'run_config':cfg,
            'image_digest':series.IMAGE_DIGEST,'docker_argv':[],
            'algorithm_config_sha256':hashlib.sha256(canonical({k:v for k,v in cfg.items() if k!='mode'})).hexdigest(),
            'algorithm_files':{'program_code/research/r8_engine/series.py':'a91e604d52b13bdd6a2acb4f4b706ae78147856d6af2c20ca7528c129639dbe4'},'base_symbol_properties_sha256':'d'*64,
            'started_at':0,'ended_at':1,'exit_code':0,'lean_log_sha256':'e'*64,
            'mode':'validation','status':'completed','failure_reason':None,'failure_t':None,
            'decisions':decisions or [],'steps':[],'orders':[],'fills':[],'voided':[],
            'funding':[],'endpoint_funding':[],'fits':fits, 'fill_forward_bars':[],
            'unexplained_cash_residual':{'per_step':[],'total':'0'}}


def test_replay_next_open_and_score_end_costs_from_source(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    actual=series.replay(historical_materialization(path),run)
    assert actual['fills']==[
        {'order_id':1,'decision_t':START,'change_t':START,'symbol':'BTCUSDT',
         'quantity':'1','price':'100.1','slippage_bps':'10','fee':'0.055055','kind':'normal'},
        {'order_id':2,'decision_t':START+4*HOUR,'change_t':START+4*HOUR,'symbol':'BTCUSDT',
         'quantity':'-1','price':'99.4','slippage_bps':'60','fee':'0.05467','kind':'score_end_liquidation'}]
    assert actual['steps'][-1]=={'t':START+4*HOUR,'cash':'99999.190275','equity':'99999.190275','positions':{}}
    assert actual['orders'][-1]=={'order_id':2,'kind':'score_end_liquidation','decision_t':START+4*HOUR,
                                  'symbol':'BTCUSDT','quantity':'-1','status':'filled'}


def observed_fixed_run(path):
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    run['orders']=[{'order_id':1,'kind':'strategy','decision_t':START,'symbol':'BTCUSDT','quantity':'1','status':'filled'},
                   {'order_id':2,'kind':'score_end_liquidation','decision_t':START+4*HOUR,'symbol':'BTCUSDT','quantity':'-1','status':'filled'}]
    run['fills']=[{'order_id':1,'decision_t':START,'change_t':START,'symbol':'BTCUSDT',
                  'quantity':'1','price':'100.1','slippage_bps':'10','fee':'0.055055','kind':'normal'},
                 {'order_id':2,'decision_t':START+4*HOUR,'change_t':START+4*HOUR,'symbol':'BTCUSDT',
                  'quantity':'-1','price':'99.4','slippage_bps':'60','fee':'0.05467','kind':'score_end_liquidation'}]
    run['steps']=[{'t':t,'cash':'100000','equity':'100000','positions':{}}
                  for t in range(START-13*DAY+HOUR,START+1,HOUR)]
    run['steps'] += [{'t':t,'cash':'99999.944945','equity':'99999.844945','positions':{'BTCUSDT':'1'}}
                     for t in range(START+HOUR,START+4*HOUR,HOUR)]
    run['steps'] += [{'t':START+4*HOUR,'cash':'99999.190275','equity':'99999.190275','positions':{}}]
    run['funding']=[{'t':START,'symbol':'BTCUSDT','q_before':'0','q_after':'1','price':'100','rate':'0','amount':'0','estimated':False}]
    return run


def test_recompute_and_period_equity_include_end_liquidation(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    report=series.recompute(path,run)
    assert report['recompute_passed'] is True
    values,sidecar=series.make_series(path,run,report)
    assert values['returns'][0] == [START//1000, -0.00000155055]
    assert values['returns'][1][1] == 0
    assert values['filled_periods']==0
    assert sidecar['produced_periods']==4
    assert values['returns'][-1][1] < 0


@pytest.mark.parametrize('section,index,field,value', [
    ('fills',0,'price','100.2'),('fills',0,'quantity','2'),('fills',0,'fee','1'),
    ('funding',0,'amount','-1'),('steps',-1,'equity','100000'),
    ('orders',0,'kind','no_trade_flatten'),
])
def test_recompute_rejects_tampered_observations(tmp_path,section,index,field,value):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run[section][index][field]=value
    report=series.recompute(path,run)
    assert not report['recompute_passed']
    with pytest.raises(series.SeriesError):
        series.make_series(path,run,report)


def test_weekly_grid_is_epoch_aligned_and_excludes_incomplete_periods():
    cfg={'sharpe_frequency_seconds':604800,'score_windows':[
        {'start':START+1,'end':START+3*7*DAY-1}]}
    assert series.periods(cfg)==[START//1000+604800]


def test_failed_run_zero_pads_grid_and_records_actual_periods(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
    report=series.recompute(path,run)
    values,sidecar=series.make_series(path,run,report)
    assert len(values['returns'])==4
    assert values['returns'][1:]==[[START//1000+i*3600,0.0] for i in range(1,4)]
    assert values['filled_periods']==3
    assert sidecar['produced_periods']==1 and sidecar['recompute_passed'] is False


def test_beta_ols_includes_intercept_and_caps():
    assert series.ols_beta([Decimal('1'),Decimal('2'),Decimal('3')],
                           [Decimal('3'),Decimal('5'),Decimal('7')]) == Decimal('2')
    assert series.ols_beta([Decimal('1'),Decimal('2'),Decimal('3')],
                           [Decimal('10'),Decimal('20'),Decimal('30')]) == Decimal('3')


def test_beta_only_uses_fit_data_and_median_for_short_history(tmp_path):
    from decimal import localcontext
    symbols=('BTCUSDT','XUSDT','YUSDT')
    daily={s:[] for s in symbols}
    with localcontext() as ctx:
        ctx.prec=50
        prices={s:Decimal('100') for s in symbols}
        for i in range(102):
            for s in symbols:
                r=Decimal(['0.01','0.02','0.03'][i%3])
                if s=='XUSDT':r=2*r+Decimal('0.01')
                if i:prices[s]*=1+r
                if s=='YUSDT' and i<92:continue
                q=str(prices[s]);daily[s].append([START-(103-i)*DAY,q,q,q,q,'1','20000000'])
    path=write_materialization(tmp_path,symbols=symbols,daily=daily)
    m=json.loads(path.read_bytes());m['warmup']['start']=START-104*DAY;path.write_bytes(canonical(m))
    data=historical_materialization(path)
    betas=series.estimate_betas(data,{'start':START-104*DAY,'end':START})
    assert abs(Decimal(betas['XUSDT'])-2)<Decimal('1e-45')
    assert abs(Decimal(betas['YUSDT'])-Decimal('1.5'))<Decimal('1e-45')
    data.daily['XUSDT'][START+DAY]={'close':Decimal('999999')}
    assert series.estimate_betas(data,{'start':START-104*DAY,'end':START})==betas


def test_baseline_is_deterministic_and_new_position_does_not_receive_gap(tmp_path):
    path=write_materialization(tmp_path)
    run=observed_fixed_run(path)
    result=series.baselines(path,run)
    assert result['beta_matched_btc_v1']['returns']==[[START//1000+i*3600,0.0] for i in range(4)]
    assert canonical(result)==canonical(series.baselines(path,run))
    assert set(result)=={'beta_matched_btc_v1','btc_perp_hold_v1'}
    assert result['btc_perp_hold_v1']['returns'][0][1]<0


def test_stress_reprices_weights_and_reports_four_fixed_scenarios(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.5'}}},
                               {'t':START+2*HOUR,'targets':{'BTCUSDT':{'weight':'0.5'}}}])
    result=series.stress(path,run)
    assert [(x['slippage_multiplier'],x['fee_rate']) for x in result['scenarios']]==[
        ('1','0.00055'),('2','0.00055'),('3','0.00055'),('2','0.00075')]
    assert Decimal(result['scenarios'][2]['net_return']) < Decimal(result['scenarios'][0]['net_return'])
    assert result['stress_passed'] is False
    assert result['breakeven']['multiplier']=='0'
    assert result['decision_approximation']


def test_stress_breakeven_is_recomputed_bracket(tmp_path):
    hourly={'BTCUSDT':[[t,'100','102','100','102' if t>=START else '100','1','100000000']
                       for t in range(START-13*DAY,START+4*HOUR,HOUR)]}
    path=write_materialization(tmp_path,hourly=hourly)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.5'}}}])
    result=series.stress(path,run)
    point=Decimal(result['breakeven']['multiplier'])
    assert Decimal('2')<point<Decimal('3')
    assert Decimal(result['breakeven']['lower_net_return'])>=0
    assert Decimal(result['breakeven']['upper_net_return'])<=0


def refresh_run_hashes(run):
    run['run_config_sha256']=series.digest(canonical(run['run_config']))
    run['algorithm_config_sha256']=series.digest(canonical({k:v for k,v in run['run_config'].items() if k!='mode'}))


def synthetic_repo(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout.decode().strip()
    git('init','-q');git('config','user.name','Offline Fixture');git('config','user.email','fixture@example.invalid')
    names=['program_code/research/r8_engine/series.py','program_code/research/r8_engine/lean_algo/framework.py',
           'program_code/research/r8_ledger/ledger.py','hypothesis.py']
    for name in names:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# synthetic source '+name+'\n')
        if name=='program_code/research/r8_engine/series.py':
            path.write_bytes(historical_series_source())
    git('add','.');git('-c','core.hooksPath=/dev/null','commit','-qm','synthetic engine')
    sha=git('rev-parse','HEAD');git('update-ref','refs/remotes/origin/main',sha)
    return root,sha,{n:series.digest((root/n).read_bytes()) for n in names},git


def iso(t):
    return datetime.fromtimestamp(t/1000,timezone.utc).isoformat().replace('+00:00','Z')


def submit_fixture(tmp_path):
    repo,sha,files,git=synthetic_repo(tmp_path)
    path=write_materialization(tmp_path,hours=32)
    book=ledger_module.ResearchLedger(tmp_path/'book')
    boundaries=list(map(iso,[START-15*DAY,START-7*DAY,START+32*HOUR,START+30*DAY,START+60*DAY]))
    reg={'hypothesis_id':'h1','generation':1,'family':'fixture','economic_mechanism':'合成測試',
         'decision_period':{'unit':'hour','value':1},'expected_holding_seconds':3600,
         'expected_turnover':1,'pessimistic_cost_ratio':.5,'data_range':{'start':boundaries[0],'end':boundaries[-1]},
         'time_splits':ledger_module.split_intervals(boundaries),'primary_metric':'after_cost_sharpe',
         'candidate_thresholds':{'sharpe':1},'multiple_testing':{'method':'BH','fdr':.05,'members':['h1'],'members_sha256':ledger_module.sha256(['h1'])},
         'max_lookback_seconds':13*86400,'label_period_seconds':3600,'max_holding_seconds':3600,
         'selection':{'type':'time_series','rule':'synthetic','known_at_period_start':boundaries[0],'symbols':['BTCUSDT']},
         'previous_no_go':None,'split_rationale':'synthetic','sharpe_frequency_seconds':3600,
         'oos_protocol':{'scheme':'expanding','initial_train_seconds':8*86400,'test_seconds':32*3600,
                         'step_seconds':32*3600,'purge_seconds':7*86400,'embargo_seconds':7*86400},
         'baselines':[{'id':'no_trade','kind':'strategy_independent'},{'id':'beta_matched_btc_v1','kind':'exposure_matched'}],
         'falsification_rule':{'degradation_z':1}}
    book.preregister(reg)
    folds=ledger_module.walk_forward_folds(reg)
    m=json.loads(path.read_bytes());m.update(purpose='research',ledger_id=book.ledger_id)
    m['window']['start']=START-15*DAY;m['warmup']={'start':START-28*DAY,'end':START-15*DAY}
    path.write_bytes(canonical(m))
    run=run_for(path,windows=[{'start':START,'end':START+32*HOUR}]);cfg=run['run_config']
    cfg.update(mode='trial',trial_id='t1',code_commit=sha,engine_commit=sha,folds=folds,
               algorithm={'path':'hypothesis.py','class':'Hypothesis'},
               strategy={'grid':[{'x':'1'}],'neighborhood':{'numeric':{'x':['1']},'categorical':[]}})
    run.update(mode='trial',algorithm_files=files)
    run['fits']=[{'fold':0,'fit_window':folds[0]['fit_window'],'selection':{
        'grid_scores':['1'],'neighborhood_means':['1'],'qualified':[True],'selected':0,
        'selected_minus_neighborhood':'0','no_trade':False},'params':{'x':'1'},'model_sha256':'f'*64}]
    run['decisions']=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.001'}}}]
    refresh_run_hashes(run)
    configuration={'strategy_parameters':{'run':{k:cfg[k] for k in (
        'initial_cash','leverage','gross_exposure_cap','decision_resolution','sharpe_frequency_seconds','algorithm','engine_commit')},'strategy':cfg['strategy']},'cost_model_parameters':cfg['cost']}
    record={'trial_id':'t1','hypothesis_id':'h1','generation':1,'parent_trial_id':None,'variant_parameters':{},
            'data_window':{k:iso(v) for k,v in m['window'].items()},'fit_window':folds[0]['fit_window'],
            'score_window':folds[0]['score_window'],'manifest_sha256':cfg['materialization_sha256'],
            'data_files':{k:v['sha256'] for k,v in m['files'].items()},'code_commit':sha,
            'configuration':configuration,'configuration_sha256':series.digest(canonical(configuration)),
            **series.RUNTIME_METADATA,'random_seed':1,'sharpe_frequency':{'unit':'hour','seconds':3600,'annualized':False},
            'evaluation_kind':'out_of_sample','role':'exploratory','folds':folds,'oos_protocol_sha256':ledger_module.sha256(reg['oos_protocol'])}
    book.begin_trial(record)
    begun=json.loads((book.out/'trials.jsonl').read_bytes().splitlines()[-1])['payload']['record']['started_at']
    query_record={**record,'started_at':begun,'finished':False,'status':'aborted'}
    run['started_at']=run['ended_at']=series.timestamp(begun)
    calls=[]
    def query(directory,trial):
        assert Path(directory)==book.out and trial=='t1'
        return {'record':copy.deepcopy({k:v for k,v in query_record.items()
                                       if k not in ('finished','status')}),
                'finished':query_record['finished'],'status':query_record['status']}
    def materialize(**kwargs):
        calls.append(kwargs)
        assert kwargs['trial']=='t1' and kwargs['hypothesis']=='h1'
        assert kwargs['window']==record['data_window']
        shutil.copytree(path.parent,kwargs['out'])
        return Path(kwargs['out'])/'materialization.json'
    rebuilt=series.replay(historical_materialization(path),run)
    for key in ('orders','fills','voided','funding','endpoint_funding','steps'):
        run[key]=rebuilt[key]
    runpath=tmp_path/'run.json'
    def submit():
        runpath.write_bytes(canonical(run))
        return series.submit(book.out,'t1',tmp_path/'unread-u1',runpath,
                             trial_query=query,materializer=materialize,repo=repo)
    return locals()


def test_submit_generated_provenance_baseline_and_real_ledger_acceptance(tmp_path):
    f=submit_fixture(tmp_path);result=f['submit']()
    assert result['status']=='completed'
    assert set(result['baseline_sha256'])=={'no_trade','beta_matched_btc_v1'}
    summary=result['result_summary'];provenance=summary['provenance']
    assert provenance['recompute_passed'] is True and len(provenance['stress_scenarios'])==4
    report=series.recompute(f['path'],f['run'])
    expected,sidecar=series.make_series(f['path'],f['run'],report)
    base=series.baselines(f['path'],f['run']);stress=series.stress(f['path'],f['run'])
    for key,value in [('series',expected),('baseline',base['beta_matched_btc_v1']),('stress',stress),('sidecar',sidecar),('recompute_report',report)]:
        sha=series.digest(canonical(value))
        assert provenance[key+'_sha256']==sha
        assert (f['book'].out/'u6_artifacts'/sha).read_bytes()==canonical(value)
    assert summary['fits']==f['run']['fits']
    assert f['calls'][0]['u1']==tmp_path/'unread-u1'


def test_fix1_17_submit_reads_real_trial_record_envelope(tmp_path):
    f = submit_fixture(tmp_path)
    queried = f['book'].trial_record('t1')
    assert set(queried) == {'record', 'finished', 'status'}
    assert queried['record']['trial_id'] == 't1'
    assert queried['finished'] is False and queried['status'] == 'aborted'
    f['runpath'].write_bytes(canonical(f['run']))
    result = series.submit(f['book'].out, 't1', tmp_path/'unread-u1', f['runpath'],
                           materializer=f['materialize'], repo=f['repo'])
    assert result['status'] == 'completed'
    assert f['book'].trial_record('t1')['finished'] is True
    with pytest.raises(series.SeriesError, match='已結束'):
        series.submit(f['book'].out, 't1', tmp_path/'unread-u1', f['runpath'],
                      materializer=f['materialize'], repo=f['repo'])


@pytest.mark.parametrize('mutation',['validation','verification','trial_id','identity','manifest','code','engine','untracked','finished','holdout','recompute'])
def test_submit_rejection_never_finishes_or_changes_ledger(tmp_path,mutation):
    f=submit_fixture(tmp_path);run=f['run'];cfg=run['run_config'];record=f['query_record']
    if mutation in ('validation','verification'):
        run['mode']=cfg['mode']=mutation
    elif mutation=='trial_id':cfg['trial_id']='other'
    elif mutation=='identity':record['configuration']['cost_model_parameters']['taker_fee_rate']='0'
    elif mutation=='manifest':
        m=json.loads(f['path'].read_bytes());m['limitations'].append('changed');f['path'].write_bytes(canonical(m))
    elif mutation=='code':(f['repo']/'hypothesis.py').write_text('# modified\n')
    elif mutation=='engine':(f['repo']/'program_code/research/r8_engine/series.py').write_text('# modified\n')
    elif mutation=='untracked':(f['repo']/'program_code/research/r8_engine/extra.py').write_text('# new\n')
    elif mutation=='finished':record['finished']=True
    elif mutation=='holdout':record['evaluation_kind']='holdout_falsification'
    elif mutation=='recompute':run['fills'][0]['fee']='0'
    refresh_run_hashes(run)
    before={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    with pytest.raises(series.SeriesError):f['submit']()
    after={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    assert after==before


def test_submit_failed_full_grid_is_accepted_and_requires_operator_stop(tmp_path):
    f=submit_fixture(tmp_path);run=f['run']
    run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
    result=f['submit']()
    assert result['status']=='failed' and result['produced_periods']==32
    summary=result['result_summary']
    assert summary['produced_periods']==1 and summary['operator_stop_required'] is True
    assert summary['provenance']['recompute_passed'] is False
    values=json.loads((f['book'].out/'series'/(result['returns_sha256']+'.json')).read_bytes())
    assert values['filled_periods']==31 and all(r[1]==0 for r in values['returns'][1:])


def test_submit_parser_has_only_authorized_inputs_and_no_status():
    parser=series.argument_parser()
    for option in ('--status','--series','--baseline','--stress','--sidecar','--model'):
        with pytest.raises(SystemExit):parser.parse_args(['submit','--ledger','b','--trial','t','--u1','u','--run','r',option,'x'])


def test_u4_subprocess_contract_does_not_read_u1_or_run_docker(tmp_path,monkeypatch):
    calls=[]
    def execute(argv,**kwargs):
        calls.append((argv,kwargs))
        return subprocess.CompletedProcess(argv,0,b'',b'')
    monkeypatch.setattr(series.subprocess,'run',execute)
    series.rematerialize(u1=tmp_path/'nonexistent',ledger=tmp_path/'book',hypothesis='h1',
                         window={'start':iso(START),'end':iso(START+HOUR)},trial='t1',out=tmp_path/'out',repo=tmp_path)
    argv=calls[0][0]
    assert argv[:3]==[sys.executable,'-m','program_code.research.r8_engine.materialize']
    assert argv[argv.index('--trial')+1]=='t1'
    assert argv[argv.index('--u1-manifest-sha256')+1]=='b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006'
    assert '--validation' not in argv and 'docker' not in argv


def seal_observation(path,run):
    refresh_run_hashes(run)
    result=series.replay(historical_materialization(path),run)
    for key in ('orders','fills','voided','funding','endpoint_funding','steps'):
        run[key]=copy.deepcopy(result[key])
    return result


def test_adjacent_windows_keep_positions_and_endpoint_funding_goes_in_last_period(tmp_path):
    path=write_materialization(tmp_path,funding={'BTCUSDT':[[START-8*HOUR,'0.01'],[START,'0.01'],[START+4*HOUR,'0.01']]})
    run=run_for(path,windows=[{'start':START,'end':START+2*HOUR},{'start':START+2*HOUR,'end':START+4*HOUR}],
                decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    result=seal_observation(path,run)
    assert [f['change_t'] for f in result['fills']]==[START,START+4*HOUR]
    assert result['endpoint_funding'][0]['amount']=='-1.02'
    assert result['steps'][13*24]['cash']=='99998.924945'  # entry plus START funding
    values,_=series.make_series(path,run,series.recompute(path,run))
    # 最後一步現金未含端點資金費；帳本最後一期含端點資金費。
    before=Decimal(result['steps'][-2]['equity']);after=Decimal(result['steps'][-1]['equity'])-Decimal('1.02')
    assert values['returns'][-1][1]==pytest.approx(float(after/before-1),abs=1e-15)


def test_delisting_partial_bar_order_identity_and_adverse_funding(tmp_path):
    delivery=START+HOUR+HOUR//2
    bars=[[t,'1','1.04','0.97','1','1000','10000000'] for t in range(START-13*DAY,START+HOUR,HOUR)]
    bars.append([START+HOUR,'1','1.02','0.95','1','500','5000000'])
    path=write_materialization(tmp_path,hours=4,hourly={'BTCUSDT':bars},
                              funding={'BTCUSDT':[[delivery,'0.02']]},
                              delistings={'BTCUSDT':{'deliveryTime':delivery,'partial_last_bar':True}})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'502.5'}}}])
    result=seal_observation(path,run)
    close=result['fills'][-1]
    assert {k:close[k] for k in ('order_id','decision_t','change_t','kind','price','fee')}=={
        'order_id':2,'decision_t':delivery,'change_t':delivery,'kind':'delisting_settlement',
        'price':'0.9443','fee':'0.2609809125'}
    assert result['funding'][-1]['q_after']=='0' and result['funding'][-1]['amount']=='-10.251'
    assert series.recompute(path,run)['recompute_passed']


def test_noop_decision_does_not_consume_order_id(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0'}}},
                                {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    result=series.replay(historical_materialization(path),run)
    assert [o['order_id'] for o in result['orders']]==[1,2]


def test_gap_symbol_not_visible_and_pending_replacement_uses_real_position(tmp_path):
    symbols=('BTCUSDT','XUSDT')
    bars=[[t,'100','100','100','100','10000','10000000'] for t in range(START-13*DAY,START+6*HOUR,HOUR) if t!=START+HOUR]
    path=write_materialization(tmp_path,hours=6,symbols=symbols,hourly={'XUSDT':bars})
    run=run_for(path,decisions=[
        {'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'1'}}},
        {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'2'}}},
        {'t':START+2*HOUR,'targets':{'BTCUSDT':{'quantity':'0'}}},
        {'t':START+3*HOUR,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'3'}}}])
    result=series.replay(historical_materialization(path),run)
    assert result['failure_reason'] is None
    assert [(f['change_t'],f['quantity']) for f in result['fills'] if f['kind']=='normal']==[
        (START,'1'),(START+2*HOUR,'1'),(START+3*HOUR,'1')]
    assert result['delayed_fills']==[{'symbol':'XUSDT','t':START+2*HOUR}]
    assert series.filled_periods(historical_materialization(path),run['run_config'],result,series.periods(run['run_config']))=={(START+HOUR)//1000,(START+2*HOUR)//1000}


def test_actual_price_exposure_drift_is_report_only(tmp_path):
    bars=[[t,'100','100','100','100','10000','10000000'] for t in range(START-13*DAY,START,HOUR)]
    bars += [[t,'200','200','200','200','10000','10000000'] for t in range(START,START+4*HOUR,HOUR)]
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.75'}}}])
    result=seal_observation(path,run)
    assert result['failure_reason'] is None and Decimal(result['max_actual_gross_exposure'])>1
    assert series.recompute(path,run)['recompute_passed']


def test_gross_cap_failed_and_false_failure_rejected(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1100'}}}])
    # 單筆上限放寬只是構造測試設定；研究設定仍由身份凍結。
    run['run_config']['cost']['order_cap_fraction']='1';seal_observation(path,run)
    with pytest.raises(series.SeriesError):series.make_series(path,run,series.recompute(path,run))
    run.update(status='failed',failure_reason='gross_exposure_cap',failure_t=START)
    values,sidecar=series.make_series(path,run,series.recompute(path,run))
    assert values['filled_periods']==4 and sidecar['produced_periods']==0
    run['failure_t']=START+HOUR
    with pytest.raises(series.SeriesError,match='曝險失敗未重現'):
        series.make_series(path,run,series.recompute(path,run))


def test_async_rotation_fails_after_increase_fills_before_delayed_reduce(tmp_path):
    bars=[[t,'100','100','100','100','100','10000000'] for t in range(START-13*DAY,START+6*HOUR,HOUR) if t!=START+HOUR]
    path=write_materialization(tmp_path,hours=6,symbols=('BTCUSDT','XUSDT'),hourly={'XUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'750'}}},
                              {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'750'},'XUSDT':{'quantity':'0'}}}])
    result=seal_observation(path,run)
    assert result['failure_reason']=='gross_exposure_cap' and result['failure_t']==START+2*HOUR
    run.update(status='failed',failure_reason='gross_exposure_cap',failure_t=START+2*HOUR)
    values,sidecar=series.make_series(path,run,series.recompute(path,run))
    assert sidecar['produced_periods']==1 and values['filled_periods']>=5


def test_fit_selection_and_params_rederived_and_no_trade_flatten(tmp_path):
    f=submit_fixture(tmp_path);run=f['run'];path=f['path']
    run['fits'][0]['selection']['selected_minus_neighborhood']='999'
    assert 'fits.0' in series.recompute(path,run)['differences']
    run['fits'][0]['selection']['selected_minus_neighborhood']='0'
    run['fits'][0]['params']={'x':'2'}
    assert 'fits.0' in series.recompute(path,run)['differences']
    # 第二折不交易：已持有部位以正常 next-open 訂單平倉。
    run['fits'][0]['params']={'x':'1'}
    fold=run['run_config']['folds'][0];end=fold['score_window']['end'];middle=iso(START+16*HOUR)
    fold['score_window']['end']=middle
    nextfold=copy.deepcopy(fold);nextfold['score_window']={'start':middle,'end':end}
    run['run_config']['folds'].append(nextfold)
    run['run_config']['score_windows']=[f['score_window'] for f in run['run_config']['folds']]
    nextfit=copy.deepcopy(run['fits'][0]);nextfit.update(fold=1,params=None,model_sha256=None,
        selection={'grid_scores':['-1'],'neighborhood_means':['-1'],'qualified':[False],'selected':None,'selected_minus_neighborhood':None,'no_trade':True})
    run['fits'].append(nextfit);result=seal_observation(path,run)
    assert result['orders'][-1]['kind']=='no_trade_flatten'
    assert result['fills'][-1]['change_t']==START+16*HOUR
    assert series.recompute(path,run)['recompute_passed']


def test_trial_quantity_target_rejected(tmp_path):
    f=submit_fixture(tmp_path);f['run']['decisions'][0]['targets']['BTCUSDT']={'quantity':'1'}
    with pytest.raises(series.SeriesError,match='quantity'):series.recompute(f['path'],f['run'])


@pytest.mark.parametrize('field',['fill_forward_bars','unexplained_cash_residual'])
def test_completed_run_cannot_hide_forward_fill_or_cash_residual(tmp_path,field):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run[field]=[{'t':START,'symbol':'BTCUSDT'}] if field=='fill_forward_bars' else {'per_step':[{'t':START,'residual':'0.0000000001'}],'total':'0'}
    with pytest.raises(series.SeriesError):series.make_series(path,run,series.recompute(path,run))


def test_filled_gap_ending_exactly_thursday_marks_recovery_week(tmp_path):
    path=write_materialization(tmp_path,hours=7*24+1);data=historical_materialization(path)
    # 構造部位與可讀切片的缺漏，不以真實行情作測試。
    gap=START-HOUR;data.hourly['BTCUSDT'].pop(gap);data.times['BTCUSDT'].remove(gap)
    cfg=run_for(path,windows=[{'start':START-7*DAY,'end':START+7*DAY}])['run_config'];cfg['sharpe_frequency_seconds']=7*86400
    record={'fills':[{'symbol':'BTCUSDT','change_t':START-2*HOUR,'quantity':'1'}],'delayed_fills':[]}
    assert series.filled_periods(data,cfg,record,series.periods(cfg))=={START//1000-7*86400,START//1000}


def test_filled_funding_blank_stale_price_delay_and_no_position_exclusions(tmp_path):
    path=write_materialization(tmp_path,hours=24,funding={'BTCUSDT':[[START,'0.001'],[START+16*HOUR,'0.001'],[START+24*HOUR,'0.001']]})
    data=historical_materialization(path);cfg=run_for(path)['run_config']
    record={'fills':[{'symbol':'BTCUSDT','change_t':START,'quantity':'1'}],'delayed_fills':[]}
    flags=series.filled_periods(data,cfg,record,series.periods(cfg))
    assert set(range(START//1000,START//1000+16*3600,3600))<=flags
    record['fills']=[]
    assert series.filled_periods(data,cfg,record,series.periods(cfg))==set()
    # 非整點結算須以 T 之前最後一根收盤計價，屬情形 3。
    data.funding['BTCUSDT']={START+HOUR//2:Decimal('0')};data.manifest['funding_interval_ms']['BTCUSDT']=100*HOUR
    record['fills']=[{'symbol':'BTCUSDT','change_t':START,'quantity':'1'}]
    record['delayed_fills']=[{'symbol':'BTCUSDT','t':START+2*HOUR}]
    assert series.filled_periods(data,cfg,record,series.periods(cfg))=={START//1000,(START+2*HOUR)//1000}


def test_beta_baseline_gap_uses_old_position_intraday_uses_adjusted_futures_equity(tmp_path):
    bars=[[t,'100','100','100','100','1000','10000000'] for t in range(START-13*DAY,START+HOUR,HOUR)]
    bars += [[START+HOUR,'200','220','200','220','1000','10000000'],
             [START+2*HOUR,'220','220','220','220','1000','10000000'],
             [START+3*HOUR,'220','220','220','220','1000','10000000']]
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'100'}}},
                              {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'300'}}}])
    cost=run['run_config']['cost'];cost.update(slippage_multiplier='0',taker_fee_rate='0')
    seal_observation(path,run)
    baseline=series.baselines(path,run)['beta_matched_btc_v1']
    assert baseline['returns'][0][1]==0
    assert baseline['returns'][1][1]==pytest.approx(149/605,abs=1e-15)
    assert baseline['returns'][2][1]==0


def test_hold_baseline_adjacent_fold_boundary_funding_is_not_double_counted(tmp_path):
    path=write_materialization(tmp_path,funding={'BTCUSDT':[[START,'0.01'],[START+2*HOUR,'0.01'],[START+4*HOUR,'0.01']]})
    run=run_for(path,windows=[{'start':START,'end':START+2*HOUR},{'start':START+2*HOUR,'end':START+4*HOUR}])
    cost=run['run_config']['cost'];cost.update(taker_fee_rate='0',slippage_multiplier='0')
    refresh_run_hashes(run)
    actual=series.baselines(path,run)['btc_perp_hold_v1']['returns']
    # 第一折 qty1000，第二折 qty989.8；邊界 T=2h 取較不利的舊部位1000。
    # 初始100000，T=0:-1020，T=2h:-1020，T=4h:-1009.596 =>96950.404。
    compounded=Decimal(1)
    for _,r in actual:compounded*=1+Decimal(str(r))
    assert float(compounded)==pytest.approx(.96950404,abs=1e-15)


def test_source_tamper_with_rehashed_manifest_still_rejected_by_submit(tmp_path):
    f=submit_fixture(tmp_path)
    name='source/kline_BTCUSDT_60.csv';file=f['path'].parent/name
    file.write_bytes(file.read_bytes().replace(b'10000000',b'10000001',1))
    m=json.loads(f['path'].read_bytes());m['files'][name]['sha256']=series.digest(file.read_bytes())
    f['path'].write_bytes(canonical(m))
    before=(f['book'].out/'trials.jsonl').read_bytes()
    with pytest.raises(series.SeriesError):f['submit']()
    assert (f['book'].out/'trials.jsonl').read_bytes()==before


def test_git_rejects_unmerged_engine_and_engine_tree_change(tmp_path):
    f=submit_fixture(tmp_path);cfg=f['run']['run_config'];git=f['git']
    target=f['repo']/'program_code/research/r8_engine/series.py';target.write_text('# changed engine\n')
    git('add','.');git('-c','core.hooksPath=/dev/null','commit','-qm','unreviewed engine')
    new=git('rev-parse','HEAD');cfg['code_commit']=new
    f['run']['algorithm_files'][target.relative_to(f['repo']).as_posix()]=series.digest(target.read_bytes())
    with pytest.raises(series.SeriesError,match='引擎目錄'):series.verify_code(f['repo'],f['run'])
    cfg['engine_commit']=new
    with pytest.raises(series.SeriesError,match='Git 完整性'):series.verify_code(f['repo'],f['run'])


def test_missing_ledger_rejected_without_creating_directory(tmp_path):
    with pytest.raises(series.SeriesError,match='帳本必須已存在'):
        series.submit(tmp_path/'missing','t1',tmp_path/'u1',tmp_path/'run')
    assert not (tmp_path/'missing').exists()


def test_daily_decision_only_midnight_and_next_day_open(tmp_path):
    path=write_materialization(tmp_path,hours=48)
    run=run_for(path,decisions=[{'t':START+DAY,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    run['run_config']['decision_resolution']='day';result=seal_observation(path,run)
    assert result['fills'][0]['change_t']==START+DAY and result['fills'][0]['price']=='100.1'
    run['decisions'][0]['t']+=HOUR;result=series.replay(historical_materialization(path),run)
    assert result['failure_reason']=='invalid_decision'


def test_pending_replacement_zero_difference_and_score_end_cancellation(tmp_path):
    bars=[[t,'100','100','100','100','1000','10000000'] for t in range(START-13*DAY,START,HOUR)]
    path=write_materialization(tmp_path,hours=4,symbols=('BTCUSDT','XUSDT'),hourly={'XUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'1'}}}])
    result=series.replay(historical_materialization(path),run)
    assert result['orders']==[{'order_id':1,'kind':'strategy','decision_t':START,'symbol':'XUSDT',
        'quantity':'1','status':'cancelled','cancel_t':START+4*HOUR,'cancel_reason':'score_end'}]
    assert not result['fills']


def test_cli_outputs_match_function_bytes(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path);record=tmp_path/'run.json';record.write_bytes(canonical(run))
    report=tmp_path/'report.json';values=tmp_path/'values.json';pressure=tmp_path/'stress.json';base=tmp_path/'base'
    for command,out,extra in [('recompute',report,[]),('series',values,['--recompute',str(report)]),('baseline',base,[]),('stress',pressure,[])]:
        assert series.main([command,'--materialization',str(path),'--run',str(record),'--out',str(out),*extra])==0
    assert report.read_bytes()==canonical(series.recompute(path,run))
    expected,sidecar=series.make_series(path,run,json.loads(report.read_bytes()))
    assert values.read_bytes()==canonical(expected) and (tmp_path/'values.json.sidecar.json').read_bytes()==canonical(sidecar)
    assert pressure.read_bytes()==canonical(series.stress(path,run))
    for name,value in series.baselines(path,run).items():assert (base/(name+'.json')).read_bytes()==canonical(value)


@pytest.mark.parametrize('field,delta,accepted',[
    ('price','0.0000001',True),('price','0.000001',False),
    ('fee','0.0000009',True),('fee','0.000002',False),
    ('quantity','0.0000000001',False),('slippage_bps','0.0000000001',False)])
def test_recompute_tolerances_and_exact_quantity_bps(tmp_path,field,delta,accepted):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run['fills'][0][field]=series.decimal_text(Decimal(run['fills'][0][field])+Decimal(delta))
    assert series.recompute(path,run)['recompute_passed'] is accepted


@pytest.mark.parametrize('location',['run','config','cost','materialization'])
def test_section7_rejects_added_fields(tmp_path,location):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    if location=='materialization':
        m=json.loads(path.read_bytes());m['extra']=1;path.write_bytes(canonical(m))
    else:
        obj={'run':run,'config':run['run_config'],'cost':run['run_config']['cost']}[location];obj['extra']=1
        refresh_run_hashes(run)
    with pytest.raises(series.SeriesError,match='§7'):series.recompute(path,run)


def test_runtime_metadata_exact_contract():
    image='sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6'
    assert series.RUNTIME_METADATA=={
        'cost_model':{'id':'r8_cost_rules','version':'r8-p4-v1'},
        'fill_model':{'id':'r8_next_open_fill','version':'r8-p4-v1'},
        'engine':{'id':'lean','version':image},'dependencies':{'lean_image_digest':image},
        'time_semantics':{'known_at':'bar_end','fill_at':'next_bar_open','simulated_latency_ms':0}}


def test_failed_run_cannot_supply_fabricated_fit_selection(tmp_path):
    f=submit_fixture(tmp_path);run=f['run']
    run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
    run['fits'][0]['selection']['selected']=None
    with pytest.raises(series.SeriesError,match='fits'):f['submit']()


def test_failed_baseline_padding_does_not_read_post_failure_prices(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
    result=series.baselines(path,run)['beta_matched_btc_v1']
    assert result['returns'][1:]==[[START//1000+i*3600,0.0] for i in range(1,4)]
    assert result['filled_periods']==3


def test_stress_full_path_hand_values_include_repriced_partial_reduce(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.5'}}},
                              {'t':START+2*HOUR,'targets':{'BTCUSDT':{'weight':'0.5'}}}])
    scenarios=series.stress(path,run)['scenarios']
    # 基準第二次目標499.6；×2 目標499.3；×3 目標499.1，非沿用基準成交量。
    # ×3 期末現金=99972.4175-.54-.0493515-1048.11-26.956391。
    # ×2／壓力費率期末現金=99962.425-.28-.052395-699.02-36.99813。
    assert [s['net_return'] for s in scenarios]==['-0.0040466261','-0.00754025385','-0.011032382425','-0.00773925525']


def test_stress_keeps_failed_scenarios_and_does_not_call_them_passed(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'1.1'}}}])
    run['run_config']['cost']['order_cap_fraction']='1';refresh_run_hashes(run)
    result=series.stress(path,run)
    assert len(result['scenarios'])==4
    assert all(s['status']=='failed' and s['failure_reason']=='gross_exposure_cap' and s['net_return'] is None for s in result['scenarios'])
    assert result['stress_passed'] is False


def test_submit_rejects_execution_before_trial_began(tmp_path):
    f=submit_fixture(tmp_path);f['run']['started_at']-=1
    before=(f['book'].out/'trials.jsonl').read_bytes()
    with pytest.raises(series.SeriesError,match='begin_trial'):f['submit']()
    assert (f['book'].out/'trials.jsonl').read_bytes()==before


def test_missing_daily_turnover_counts_zero_and_recent_listing_blocks_open(tmp_path):
    path=write_materialization(tmp_path);data=historical_materialization(path);cost=cost_parameters()
    for t in list(data.daily['BTCUSDT'])[-7:]:data.daily['BTCUSDT'].pop(t)
    assert data.liquidity('BTCUSDT',START,cost)==(Decimal(0),Decimal('10000000'),True)
    data.manifest['first_bar']['BTCUSDT']=START-11*DAY
    assert data.liquidity('BTCUSDT',START,cost)[2] is False


@pytest.mark.parametrize('turnover,bps',[('100000000','5'),('10000000','10'),('1000000','20')])
def test_three_liquidity_tiers(turnover,bps):
    assert series.order_segments('0','1','100','0.1','0',turnover,'10000000',True,cost_parameters())[0]['slippage_bps']==bps


def test_nonhour_delisting_funding_uses_partial_close_not_previous_complete_close(tmp_path):
    delivery=START+HOUR+HOUR//2
    bars=[[t,'1','1.04','0.97','1','1000','10000000'] for t in range(START-13*DAY,START+HOUR,HOUR)]
    bars.append([START+HOUR,'1','1.02','0.85','0.9','500','5000000'])
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars},funding={'BTCUSDT':[[delivery,'0.02']]},
        delistings={'BTCUSDT':{'deliveryTime':delivery,'partial_last_bar':True}})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'502.5'}}}])
    result=seal_observation(path,run)
    assert result['funding'][-1]['price']=='0.9'
    assert result['funding'][-1]['amount']=='-9.2259'
    assert series.recompute(path,run)['recompute_passed']


def test_hold_baseline_full_equity_is_independent_of_hypothesis_cap(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    original=series.baselines(path,run)['btc_perp_hold_v1']
    run['run_config']['gross_exposure_cap']='0.25';refresh_run_hashes(run)
    assert series.baselines(path,run)['btc_perp_hold_v1']==original


def test_arbitrary_neighbor_index_lists_cannot_make_isolated_peak_qualify():
    grid=[{'x':i} for i in range(3)]
    with pytest.raises(series.SeriesError,match='鄰域'):
        series.select_grid_point(grid,[[0],[1],[2]],['-1','100','-1'])
    declared={'numeric':{'x':[0,1,2]},'categorical':[]}
    assert series.select_grid_point(grid,declared,['-1','100','-1'])['no_trade']


def test_numeric_neighborhood_axes_must_be_ordered():
    with pytest.raises(series.SeriesError,match='數值軸'):
        series.select_grid_point([{'x':i} for i in range(3)],
            {'numeric':{'x':[1,0,2]},'categorical':[]},['-1','100','-1'])


def test_materialization_read_boundary_excludes_lean_custom_payloads(tmp_path,monkeypatch):
    # §6.0 列明只讀 materialization.json、source/ 切片及 overlay；
    # 「每個檔案」指此讀取範圍。§7.1 files 同時列出供 U5 掛載的 lean/custom，
    # 其 payload 檢查屬 §5 U5；U6 僅在 submit 比對其身份雜湊，不讀這些 payload。
    path=write_materialization(tmp_path);manifest=json.loads(path.read_bytes())
    for name in ('lean/example.zip','custom/example.csv'):
        manifest['files'][name]={'sha256':'f'*64,'rows':1,'first':START,'last':START,
                                  'source_file':'synthetic','source_sha256':'e'*64}
    path.write_bytes(canonical(manifest));read=Path.read_bytes;opened=[]
    def bounded_read(file):
        name=file.relative_to(path.parent).as_posix()
        assert not name.startswith(('lean/','custom/'))
        opened.append(name);return read(file)
    monkeypatch.setattr(Path,'read_bytes',bounded_read)
    historical_materialization(path)
    assert set(opened)=={'materialization.json','symbol_properties_overlay.csv',
        'source/kline_BTCUSDT_60.csv','source/kline_BTCUSDT_D.csv',
        'source/funding_BTCUSDT_funding.csv','source/open_interest_BTCUSDT_4h.csv'}


@pytest.mark.parametrize('windows', [[], [{'start': START, 'end': START+2*HOUR}],
    [{'start': START, 'end': START+2*HOUR}, {'start': START+2*HOUR, 'end': START+4*HOUR}]])
def test_fix1_02_validation_without_folds_requires_materialized_window(tmp_path, windows):
    path = write_materialization(tmp_path)
    run = run_for(path)
    run['run_config']['score_windows'] = windows
    refresh_run_hashes(run)
    with pytest.raises(series.SeriesError):
        series.recompute(path, run)


def test_fix1_02_validation_uses_explicit_full_window(tmp_path):
    path = write_materialization(tmp_path)
    run = observed_fixed_run(path)
    assert run['run_config']['folds'] == []
    assert series.recompute(path, run)['recompute_passed'] is True
    assert len(series.make_series(path, run, series.recompute(path, run))[0]['returns']) == 4


@pytest.mark.parametrize('resolution,decision_offset,recovery', [('hour', HOUR, 3*HOUR), ('day', DAY, DAY+HOUR)])
def test_fix1_04_gap_keeps_pending_flat_symbol_and_resumes(tmp_path, resolution, decision_offset, recovery):
    bars = [[t,'100','100','100','100','10000','10000000']
            for t in range(START-13*DAY, START+recovery+2*HOUR, HOUR)
            if t < START or t >= START+recovery]
    path = write_materialization(tmp_path, hours=recovery//HOUR+2,
                                 symbols=('BTCUSDT','XUSDT'), hourly={'XUSDT':bars})
    run = run_for(path, decisions=[
        {'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'1'}}},
        {'t':START+decision_offset,'targets':{'BTCUSDT':{'quantity':'0'}}}])
    run['run_config']['decision_resolution'] = resolution
    result = seal_observation(path,run)
    assert result['failure_reason'] is None
    assert result['orders'][0]['status'] == 'filled'
    assert result['fills'][0]['change_t'] == START+recovery
    assert result['fills'][0]['quantity'] == '1'
    assert not any(o.get('cancel_reason') == 'replaced' for o in result['orders'])
    assert series.recompute(path,run)['recompute_passed']
    run['decisions'][1]['targets']['XUSDT'] = {'quantity':'0'}
    assert series.replay(historical_materialization(path),run)['failure_reason'] == 'invalid_decision'


def test_fix1_03_sections_sorted_by_contract_and_reversal_reduce_first(tmp_path):
    bars = [[t,'100','100','100','100','10000','10000000']
            for t in range(START-13*DAY, START+5*HOUR, HOUR)
            if t not in (START, START+HOUR)]
    path = write_materialization(tmp_path, hours=5, symbols=('BTCUSDT','XUSDT'), hourly={'XUSDT':bars})
    run = run_for(path, decisions=[
        {'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'1'}}},
        {'t':START+2*HOUR,'targets':{'BTCUSDT':{'quantity':'2'}}},
        {'t':START+3*HOUR,'targets':{'BTCUSDT':{'quantity':'-1'},'XUSDT':{'quantity':'1'}}}])
    result = seal_observation(path,run)
    assert [(f['order_id'], f['quantity']) for f in result['fills'][:4]] == [(1,'1'),(2,'2'),(3,'-2'),(3,'-1')]
    for key in ('orders','voided'):
        assert result[key] == sorted(result[key],key=lambda r:r['order_id'])
    for key in ('funding','endpoint_funding'):
        assert result[key] == sorted(result[key],key=lambda r:(r['t'],r['symbol']))
    assert series.recompute(path,run)['recompute_passed']
    run['fills'][0],run['fills'][1] = run['fills'][1],run['fills'][0]
    assert not series.recompute(path,run)['recompute_passed']


def no_trade_gap_run(tmp_path):
    bars = [[t,'100','100','100','100','10000','10000000']
            for t in range(START-13*DAY, START+6*HOUR, HOUR)
            if t < START or t >= START+3*HOUR]
    path = write_materialization(tmp_path,hours=6,symbols=('BTCUSDT','XUSDT'),hourly={'BTCUSDT':bars})
    run = run_for(path, windows=[{'start':START,'end':START+HOUR},
        {'start':START+HOUR,'end':START+3*HOUR}, {'start':START+3*HOUR,'end':START+6*HOUR}],
        decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'},'XUSDT':{'quantity':'0'}}},
                   {'t':START+4*HOUR,'targets':{'BTCUSDT':{'quantity':'1'},'XUSDT':{'quantity':'0'}}}])
    run['fits'][1].update(params=None,model_sha256=None,selection={
        'grid_scores':['-1'],'neighborhood_means':['-1'],'qualified':[False],
        'selected':None,'selected_minus_neighborhood':None,'no_trade':True})
    return path,run


def test_fix1_05_no_trade_flatten_is_order_not_decision(tmp_path):
    path = write_materialization(tmp_path)
    run = run_for(path, windows=[{'start':START,'end':START+2*HOUR},
        {'start':START+2*HOUR,'end':START+4*HOUR}],
        decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    run['fits'][1].update(params=None,model_sha256=None,selection={
        'grid_scores':['-1'],'neighborhood_means':['-1'],'qualified':[False],
        'selected':None,'selected_minus_neighborhood':None,'no_trade':True})
    decisions = copy.deepcopy(run['decisions'])
    result = seal_observation(path,run)
    assert run['decisions'] == decisions
    assert result['orders'][1] == {'order_id':2,'kind':'no_trade_flatten',
        'decision_t':START+2*HOUR,'symbol':'BTCUSDT','quantity':'-1','status':'filled'}
    assert series.recompute(path,run)['recompute_passed']
    run['decisions'].append({'t':START+2*HOUR,'targets':{'BTCUSDT':{'quantity':'0'}}})
    assert not series.recompute(path,run)['recompute_passed']


def test_fix1_06_zero_difference_replacement_cancels_without_order_id(tmp_path):
    path,run = no_trade_gap_run(tmp_path)
    result = seal_observation(path,run)
    assert result['orders'][0] == {'order_id':1,'kind':'strategy','decision_t':START,
        'symbol':'BTCUSDT','quantity':'1','status':'cancelled','cancel_t':START+HOUR,
        'cancel_reason':'no_trade'}
    assert [o['order_id'] for o in result['orders']] == [1,2,3]
    assert result['voided'] == []
    assert result['fills'][0]['order_id'] == 2
    assert series.recompute(path,run)['recompute_passed']


@pytest.mark.parametrize('reason', ['algorithm_exception','lean_error','fill_forward_bar','invalid_decision'])
@pytest.mark.parametrize('corruption', ['earlier_cap','fill','step'])
def test_fix1_10_failed_run_rejects_earlier_failure_or_prefix_difference(tmp_path, reason, corruption):
    path = write_materialization(tmp_path)
    run = observed_fixed_run(path)
    run.update(status='failed',failure_reason=reason,failure_t=START+3*HOUR)
    if corruption == 'earlier_cap':
        run['decisions'][0]['targets']['BTCUSDT']['quantity'] = '1100'
        run['run_config']['cost']['order_cap_fraction'] = '1'
        refresh_run_hashes(run)
    elif corruption == 'fill':
        run['fills'][0]['fee'] = '1'
    else:
        run['steps'][13*24]['cash'] = '1'
    with pytest.raises(series.SeriesError):
        series.make_series(path,run,series.recompute(path,run))


@pytest.mark.parametrize('reason', ['algorithm_exception','lean_error','fill_forward_bar','invalid_decision'])
def test_fix1_10_external_failure_checks_strict_prefix_and_zeroes_boundary_period(tmp_path, reason):
    path = write_materialization(tmp_path)
    run = observed_fixed_run(path)
    run.update(status='failed',failure_reason=reason,failure_t=START+2*HOUR)
    run['decisions'].append({'t':START+2*HOUR,'targets':{'BTCUSDT':{'quantity':'9999'}}})
    run['steps'][-1]['cash'] = '1'
    if reason == 'fill_forward_bar':
        run['fill_forward_bars'] = [{'t':START+2*HOUR,'symbol':'BTCUSDT'}]
    report = series.recompute(path,run)
    assert report['differences'] == []
    assert report['recompute_passed'] is False
    values,sidecar = series.make_series(path,run,report)
    assert values['returns'][0][1] == pytest.approx(-0.00000155055, abs=1e-16)
    assert values['returns'][1:] == [[START//1000+i*3600,0.0] for i in range(1,4)]
    assert values['filled_periods'] == 3 and sidecar['produced_periods'] == 1


def test_fix1_10_unknown_failure_time_skips_temporal_evidence_and_zeroes_grid(tmp_path):
    path = write_materialization(tmp_path)
    run = observed_fixed_run(path)
    run.update(status='failed',failure_reason='lean_error',failure_t=None,
               decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'9999'}}}],
               fits=[{'malformed':'unavailable time prefix'}])
    run['steps'][0]['cash'] = '1'
    report = series.recompute(path,run)
    assert report['differences'] == []
    values,sidecar = series.make_series(path,run,report)
    assert values['returns'] == [[START//1000+i*3600,0.0] for i in range(4)]
    assert values['filled_periods'] == 4 and sidecar['produced_periods'] == 0
    run['run_config_sha256'] = '0'*64
    with pytest.raises(series.SeriesError,match='雜湊'):
        series.recompute(path,run)


def test_fix1_11_baseline_does_not_price_unlisted_zero_position(tmp_path):
    days = [[START-i*DAY,'100','100','100','100','1','20000000'] for i in range(103,0,-1)]
    bars = [[START+i*HOUR,'100','100','100','100','1','10000000'] for i in range(2,4)]
    path = write_materialization(tmp_path,symbols=('BTCUSDT','XUSDT'),
        hourly={'XUSDT':bars},daily={'BTCUSDT':days,'XUSDT':[]})
    manifest = json.loads(path.read_bytes())
    manifest['warmup']['start'] = START-104*DAY
    manifest['first_bar']['XUSDT'] = START+2*HOUR
    path.write_bytes(canonical(manifest))
    run = run_for(path)
    result = series.baselines(path,run)
    assert result['beta_matched_btc_v1']['returns'] == [[START//1000+i*3600,0.0] for i in range(4)]


@pytest.mark.parametrize('later_step', [False,True])
def test_fix1_12_missing_endpoint_cancels_and_liquidates_without_future_price(tmp_path, later_step):
    bars = [[t,'100','100','100','100','10000','10000000']
            for t in range(START-13*DAY, START+HOUR, HOUR)]
    if later_step:
        bars.append([START+5*HOUR,'900','900','900','900','10000','10000000'])
    path = write_materialization(tmp_path,hours=8,hourly={'BTCUSDT':bars})
    run = run_for(path,windows=[{'start':START,'end':START+4*HOUR}],decisions=[
        {'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}},
        {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'2'}}}])
    result = seal_observation(path,run)
    assert START+4*HOUR not in [s['t'] for s in result['steps']]
    assert result['orders'][1] == {'order_id':2,'kind':'strategy','decision_t':START+HOUR,
        'symbol':'BTCUSDT','quantity':'1','status':'cancelled',
        'cancel_t':START+(6 if later_step else 8)*HOUR,'cancel_reason':'score_end'}
    assert [(f['change_t'],f['price']) for f in result['fills']] == [(START,'100.1'),(START+4*HOUR,'99.4')]
    assert result['fills'][-1]['kind'] == 'score_end_liquidation'
    assert series.recompute(path,run)['recompute_passed']
    values,_ = series.make_series(path,run,series.recompute(path,run))
    assert values['filled_periods'] == 3


def test_fix1_13_delayed_fill_exposure_checked_after_same_step_delisting(tmp_path):
    base = [[t,'100','100','100','100','10000','10000000']
            for t in range(START-13*DAY, START+6*HOUR, HOUR)]
    path = write_materialization(tmp_path,hours=6,symbols=('BTCUSDT','XUSDT'),
        hourly={'BTCUSDT':[r for r in base if r[0]!=START+HOUR],
                'XUSDT':[r for r in base if r[0]<START+HOUR]},
        delistings={'XUSDT':{'deliveryTime':START+3*HOUR,'partial_last_bar':False}})
    run = run_for(path,decisions=[
        {'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'750'}}},
        {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'750'},'XUSDT':{'quantity':'0'}}}])
    result = seal_observation(path,run)
    assert result['failure_reason'] is None
    step = next(s for s in result['steps'] if s['t']==START+3*HOUR)
    assert step['positions'] == {'BTCUSDT':'750'}
    assert any(f['change_t']==START+2*HOUR and f['symbol']=='BTCUSDT' for f in result['fills'])
    assert any(f['change_t']==START+3*HOUR and f['kind']=='delisting_settlement' for f in result['fills'])
    assert series.recompute(path,run)['recompute_passed']


@pytest.mark.parametrize('turnover,net', [('200000000',-.0021),('20000000',-.0031),('2000000',-.0051)])
def test_fix1_15_btc_hold_fold_exit_uses_liquidity_tier_not_penalty(tmp_path, turnover, net):
    daily = [[t,'100','100','100','100','1',turnover] for t in range(START-13*DAY,START,DAY)]
    path = write_materialization(tmp_path,daily={'BTCUSDT':daily})
    run = run_for(path)
    result = series.baselines(path,run)['btc_perp_hold_v1']
    product = Decimal(1)
    for _,value in result['returns']:
        product *= 1+Decimal(str(value))
    assert float(product-1) == pytest.approx(net,abs=1e-15)
    assert canonical(result) == canonical(series.baselines(path,run)['btc_perp_hold_v1'])


def test_fix1_16_beta_includes_daily_bar_ending_at_fit_end(tmp_path):
    days=[]
    for i in range(91):
        price = '100' if i%2 else '110'
        days.append([START-(91-i)*DAY,price,price,price,price,'1','20000000'])
    path = write_materialization(tmp_path,symbols=('BTCUSDT','XUSDT','YUSDT'),
        daily={'BTCUSDT':days,'XUSDT':days,'YUSDT':[]})
    m=json.loads(path.read_bytes());m['warmup']['start']=START-92*DAY;path.write_bytes(canonical(m))
    data=historical_materialization(path)
    expected={'BTCUSDT':'1','XUSDT':'1','YUSDT':'1'}
    assert series.estimate_betas(data,{'start':START-92*DAY,'end':START}) == expected
    data.daily['XUSDT'][START]={'close':Decimal('99999')}
    assert series.estimate_betas(data,{'start':START-92*DAY,'end':START}) == expected


def test_fix1_18_manifest_uses_u4_dataset_names_and_preserves_gap_semantics(tmp_path):
    bars = [[t,'100','100','100','100','10000','10000000']
            for t in range(START-13*DAY,START+4*HOUR,HOUR) if t!=START+HOUR]
    gaps={'BTCUSDT':{'kline_hour':[{'start':START+HOUR,'end_exclusive':START+2*HOUR,'count':1}],
                    'kline_day':[],'open_interest':[{'start':START,'end_exclusive':START+4*HOUR,'count':1}],
                    'funding':[]}}
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars},gaps=gaps)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    seal_observation(path,run)
    assert historical_materialization(path).manifest['gaps']==gaps
    values,_=series.make_series(path,run,series.recompute(path,run))
    assert values['filled_periods']==2


@pytest.mark.parametrize('legacy', ['kline_60','kline_D','hourly','daily'])
def test_fix1_18_manifest_rejects_non_u4_dataset_names(tmp_path, legacy):
    path=write_materialization(tmp_path,gaps={'BTCUSDT':{legacy:[]}})
    with pytest.raises(series.SeriesError,match='gaps'):
        historical_materialization(path)


@pytest.mark.parametrize('corruption',['earlier_failure','prefix_fee','missing_fit'])
def test_fix1_10_failed_submit_rejects_prefix_without_writing_ledger(tmp_path,corruption):
    f=submit_fixture(tmp_path);run=f['run']
    run.update(status='failed',failure_reason='lean_error',failure_t=START+3*HOUR)
    if corruption=='earlier_failure':
        run['decisions'][0]['targets']={'UNLISTED':{'weight':'0'}}
    elif corruption=='prefix_fee':
        run['fills'][0]['fee']='10'
    else:
        run['fits']=[]
    refresh_run_hashes(run)
    before={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    with pytest.raises(series.SeriesError):
        f['submit']()
    after={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    assert after==before


def test_fix1_10_unknown_failure_time_real_ledger_submission_requires_stop(tmp_path):
    f=submit_fixture(tmp_path)
    f['run'].update(status='failed',failure_reason='lean_error',failure_t=None,
                    fits=[],decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'9999'}}}])
    f['runpath'].write_bytes(canonical(f['run']))
    result=series.submit(f['book'].out,'t1',tmp_path/'unread-u1',f['runpath'],
                         materializer=f['materialize'],repo=f['repo'])
    assert result['status']=='failed'
    assert result['result_summary']['operator_stop_required'] is True
    assert result['result_summary']['produced_periods']==0
    values=json.loads((f['book'].out/'series'/(result['returns_sha256']+'.json')).read_bytes())
    assert values['filled_periods']==32 and all(row[1]==0 for row in values['returns'])
    assert f['book'].trial_record('t1')['status']=='failed'


@pytest.mark.parametrize('entry',['recompute','submit'])
def test_fix1_10_gross_exposure_failure_requires_concrete_time_before_ledger_write(tmp_path,entry):
    f=submit_fixture(tmp_path)
    f['run'].update(status='failed',failure_reason='gross_exposure_cap',failure_t=None)
    f['runpath'].write_bytes(canonical(f['run']))
    before={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    with pytest.raises(series.SeriesError,match='failure_t'):
        if entry=='recompute':
            series.recompute(f['path'],f['run'])
        else:
            series.submit(f['book'].out,'t1',tmp_path/'unread-u1',f['runpath'],
                          materializer=f['materialize'],repo=f['repo'])
    after={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    assert after==before


# FIX2 的觀測值獨立寫定，對照 U5 framework.py 的事件與 lean_runner.py 的排序；
# 不以 replay／seal_observation 產生 orders、fills、funding 或 steps。
def u5_step(hour, positions=None, cash='100000', equity=None):
    return {'t':START+hour*HOUR, 'cash':cash, 'equity':equity or cash,
            'positions':positions or {}}


def u5_order(number, hour, symbol, quantity, *, kind='strategy', status='filled', **extra):
    return {'order_id':number, 'kind':kind, 'decision_t':START+hour*HOUR,
            'symbol':symbol, 'quantity':quantity, 'status':status, **extra}


def u5_fill(number, decision_hour, change_hour, symbol, quantity, *, kind='normal',
            price='100', bps='0', fee='0'):
    return {'order_id':number, 'decision_t':START+decision_hour*HOUR,
            'change_t':START+change_hour*HOUR, 'symbol':symbol, 'quantity':quantity,
            'price':price, 'slippage_bps':bps, 'fee':fee, 'kind':kind}


def u5_case(tmp_path, bar_hours, *, hours=6, decisions=None, windows=None, funding=None):
    # 固定 100 元、無成交成本的構造案例，隔離事件順序；G1–G8 另驗精確成本。
    bars={s:[[START+h*HOUR,'100','100','100','100','10000','10000000'] for h in hs]
          for s,hs in bar_hours.items()}
    path=write_materialization(tmp_path,hours=hours,symbols=tuple(bar_hours),hourly=bars,
        funding=funding or {s:[[START-HOUR,'0']] for s in bar_hours})
    run=run_for(path,decisions=decisions,windows=windows)
    cost=run['run_config']['cost']
    cost.update(taker_fee_rate='0',forced_reduce_penalty_bps='0',order_cap_fraction='1')
    for tier in cost['slippage_tiers_bps']:
        tier['bps']='0'
    refresh_run_hashes(run)
    return path,run


@pytest.mark.parametrize('pending', [False, True])
def test_fix2_04_u5_failure_omits_pending_and_rejected_decision_orders(tmp_path, pending):
    decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}]
    if not pending:
        decisions += [{'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'1100'}}}]
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0,3]},decisions=decisions)
    if pending:
        # 首筆尚未成交，失敗前不應憑空出現 cancelled 訂單。
        run['decisions'][0]['t']=START+HOUR
        run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
        run['steps']=[u5_step(0),u5_step(1)]
    else:
        run.update(status='failed',failure_reason='gross_exposure_cap',failure_t=START+HOUR)
        run['orders']=[u5_order(1,0,'BTCUSDT','1')]
        run['fills']=[u5_fill(1,0,0,'BTCUSDT','1')]
        run['steps']=[u5_step(0)]
    refresh_run_hashes(run)
    report=series.recompute(path,run)
    assert report['differences']==[]
    assert report['recompute_passed'] is False
    values,sidecar=series.make_series(path,run,report)
    assert len(values['returns'])==6 and sidecar['recompute_passed'] is False


@pytest.mark.parametrize('last_step', [1,2])
def test_fix2_05_u5_tail_funding_uses_materialized_end(tmp_path,last_step):
    funds=[[START-2*HOUR,'0'],[START,'0'],[START+2*HOUR,'0.01'],[START+4*HOUR,'0.02']]
    path,run=u5_case(tmp_path,{'BTCUSDT':list(range(-1,last_step))},hours=4,
        decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}],funding={'BTCUSDT':funds})
    run['orders']=[u5_order(1,0,'BTCUSDT','1'),u5_order(2,4,'BTCUSDT','-1',kind='score_end_liquidation')]
    run['fills']=[u5_fill(1,0,0,'BTCUSDT','1'),u5_fill(2,4,4,'BTCUSDT','-1',kind='score_end_liquidation')]
    run['steps']=[u5_step(0)]+[u5_step(h,{'BTCUSDT':'1'}) for h in range(1,last_step+1)]
    run['funding']=[{'t':START,'symbol':'BTCUSDT','q_before':'0','q_after':'1','price':'100',
                     'rate':'0','amount':'0','estimated':False},
                    {'t':START+2*HOUR,'symbol':'BTCUSDT','q_before':'1','q_after':'1','price':'100',
                     'rate':'0.01','amount':'-1.02','estimated':False}]
    run['endpoint_funding']=[{'t':START+4*HOUR,'symbol':'BTCUSDT','q_before':'1','q_after':'0','price':'100',
                             'rate':'0.02','amount':'-2.04','estimated':False}]
    report=series.recompute(path,run)
    assert report['recompute_passed'], report['differences']
    assert report['max_difference']=='0'
    values,_=series.make_series(path,run,report)
    assert values['returns'][-1][1]==pytest.approx(-2.04/99998.98,abs=1e-16)
    assert values['returns'][2][1]==pytest.approx(-1.02/100000,abs=1e-16)


@pytest.mark.parametrize('later_step', [False,True])
def test_fix2_06_u5_missing_score_end_cancels_at_processing_time(tmp_path,later_step):
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0]+([5] if later_step else [])},hours=8,
        windows=[{'start':START,'end':START+4*HOUR}],decisions=[
            {'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}},
            {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'2'}}}])
    run['orders']=[u5_order(1,0,'BTCUSDT','1'),
        u5_order(2,1,'BTCUSDT','1',status='cancelled',cancel_t=START+(6 if later_step else 8)*HOUR,cancel_reason='score_end'),
        u5_order(3,4,'BTCUSDT','-1',kind='score_end_liquidation')]
    run['fills']=[u5_fill(1,0,0,'BTCUSDT','1'),u5_fill(3,4,4,'BTCUSDT','-1',kind='score_end_liquidation')]
    run['steps']=[u5_step(0),u5_step(1,{'BTCUSDT':'1'})]+([u5_step(6)] if later_step else [])
    report=series.recompute(path,run)
    assert report['recompute_passed'],report['differences']
    assert report['max_difference']=='0'


def test_fix2_06_u5_equal_score_end_settles_before_exposure(tmp_path):
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0,2],'XUSDT':[-1,0,4]},
        windows=[{'start':START,'end':START+3*HOUR}],decisions=[
            {'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'750'}}},
            {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'750'},'XUSDT':{'quantity':'0'}}}])
    run['orders']=[u5_order(1,0,'XUSDT','750'),u5_order(2,1,'BTCUSDT','750'),
        u5_order(3,1,'XUSDT','-750',status='cancelled',cancel_t=START+3*HOUR,cancel_reason='score_end'),
        u5_order(4,3,'BTCUSDT','-750',kind='score_end_liquidation'),
        u5_order(5,3,'XUSDT','-750',kind='score_end_liquidation')]
    run['fills']=[u5_fill(1,0,0,'XUSDT','750'),u5_fill(2,1,2,'BTCUSDT','750'),
        u5_fill(4,3,3,'BTCUSDT','-750',kind='score_end_liquidation'),
        u5_fill(5,3,3,'XUSDT','-750',kind='score_end_liquidation')]
    run['steps']=[u5_step(0),u5_step(1,{'XUSDT':'750'}),u5_step(3),u5_step(5)]
    report=series.recompute(path,run)
    assert report['recompute_passed'],report['differences']
    assert report['max_difference']=='0'


@pytest.mark.parametrize('all_invisible', [False,True])
def test_fix2_03_u5_no_trade_cancels_all_and_flattens_on_visibility(tmp_path,all_invisible):
    path,run=u5_case(tmp_path,{'BTCUSDT':list(range(-1,6)),'XUSDT':[-1,0,3,4,5]},
        windows=[{'start':START,'end':START+2*HOUR},{'start':START+2*HOUR,'end':START+6*HOUR}],
        decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'1'}}},
                   {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'2'}}}])
    if all_invisible:
        # BTC 只作基準訂閱；它產生時間步，該步策略標的集合仍為空。
        manifest=json.loads(path.read_bytes());manifest['strategy_symbols']=['XUSDT']
        path.write_bytes(canonical(manifest))
        run['materialization_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        run['run_config']['materialization_sha256']=run['materialization_sha256']
        run['run_config']['symbols']=['XUSDT']
        for decision in run['decisions']:
            decision['targets'].pop('BTCUSDT')
    run['fits'][1].update(params=None,model_sha256=None,selection={
        'grid_scores':['-1'],'neighborhood_means':['-1'],'qualified':[False],
        'selected':None,'selected_minus_neighborhood':None,'no_trade':True})
    refresh_run_hashes(run)
    run['orders']=[u5_order(1,0,'XUSDT','1'),
        u5_order(2,1,'XUSDT','1',status='cancelled',cancel_t=START+2*HOUR,cancel_reason='no_trade'),
        u5_order(3,4,'XUSDT','-1',kind='no_trade_flatten')]
    run['fills']=[u5_fill(1,0,0,'XUSDT','1'),u5_fill(3,4,4,'XUSDT','-1')]
    run['steps']=[u5_step(0)]+[u5_step(h,{'XUSDT':'1'}) for h in range(1,5)]+[u5_step(5),u5_step(6)]
    report=series.recompute(path,run)
    assert report['recompute_passed'],report['differences']
    assert report['max_difference']=='0'


@pytest.mark.parametrize('quantity,failed', [('200',False),('750',True)])
def test_fix2_02_u5_gap_pending_keeps_last_decision_price(tmp_path,quantity,failed):
    path,run=u5_case(tmp_path,{'BTCUSDT':list(range(-1,6)),'XUSDT':[-1,3,4,5]},decisions=[
        {'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':quantity}}},
        {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'750'}}}])
    # 缺漏後成交價跳至 900；曝險仍以最近決策時已知的 100 計算。
    source=path.parent/'source/kline_XUSDT_60.csv'
    rows=list(csv.reader(io.StringIO(source.read_text())))
    for row in rows[2:]:
        row[1:5]=['900']*4
    buf=io.StringIO(newline='');csv.writer(buf).writerows(rows);source.write_text(buf.getvalue())
    manifest=json.loads(path.read_bytes())
    manifest['files']['source/kline_XUSDT_60.csv']['sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    path.write_bytes(canonical(manifest))
    run['materialization_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    run['run_config']['materialization_sha256']=run['materialization_sha256'];refresh_run_hashes(run)
    run['orders']=[u5_order(1,0,'XUSDT',quantity),u5_order(2,1,'BTCUSDT','750')]
    run['fills']=[u5_fill(2,1,1,'BTCUSDT','750'),u5_fill(1,0,3,'XUSDT',quantity,price='900')]
    run['steps']=[u5_step(0),u5_step(1),u5_step(2,{'BTCUSDT':'750'}),u5_step(3,{'BTCUSDT':'750'})]
    if failed:
        run.update(status='failed',failure_reason='gross_exposure_cap',failure_t=START+4*HOUR)
    else:
        run['orders'] += [u5_order(3,6,'BTCUSDT','-750',kind='score_end_liquidation'),
                          u5_order(4,6,'XUSDT','-200',kind='score_end_liquidation')]
        run['fills'] += [u5_fill(3,6,6,'BTCUSDT','-750',kind='score_end_liquidation'),
                        u5_fill(4,6,6,'XUSDT','-200',kind='score_end_liquidation',price='900')]
        run['steps'] += [u5_step(4,{'BTCUSDT':'750','XUSDT':'200'}),u5_step(5,{'BTCUSDT':'750','XUSDT':'200'}),u5_step(6)]
    report=series.recompute(path,run)
    assert report['differences']==[]
    assert report['max_difference']=='0'
    assert report['recompute_passed'] is not failed


@pytest.mark.parametrize('section,field,value', [('orders','decision_t',START),('fills','price','101'),
    ('steps','cash','99999')])
def test_fix2_08_u5_independent_observation_tampering_is_detected(tmp_path,section,field,value):
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0,1]},hours=2,
        decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    run['orders']=[u5_order(1,0,'BTCUSDT','1'),u5_order(2,2,'BTCUSDT','-1',kind='score_end_liquidation')]
    run['fills']=[u5_fill(1,0,0,'BTCUSDT','1'),u5_fill(2,2,2,'BTCUSDT','-1',kind='score_end_liquidation')]
    run['steps']=[u5_step(0),u5_step(1,{'BTCUSDT':'1'}),u5_step(2)]
    assert series.recompute(path,run)['recompute_passed']
    run[section][-1][field]=value
    report=series.recompute(path,run)
    assert report['recompute_passed'] is False
    assert any(d.startswith(section+'.') for d in report['differences'])


@pytest.mark.parametrize('resolution', ['hour','day'])
def test_fix2_03_u5_visible_zero_targets_do_not_replace_pending_flatten(tmp_path,resolution):
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0,1,4,5],'XUSDT':[-1,0,3,4,5]},
        windows=[{'start':START,'end':START+2*HOUR},{'start':START+2*HOUR,'end':START+6*HOUR}],
        decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'},'XUSDT':{'quantity':'1'}}}])
    run['run_config']['decision_resolution']=resolution
    run['fits'][1].update(params=None,model_sha256=None,selection={
        'grid_scores':['-1'],'neighborhood_means':['-1'],'qualified':[False],
        'selected':None,'selected_minus_neighborhood':None,'no_trade':True})
    refresh_run_hashes(run)
    run['orders']=[u5_order(1,0,'BTCUSDT','1'),u5_order(2,0,'XUSDT','1'),
        u5_order(3,2,'BTCUSDT','-1',kind='no_trade_flatten'),u5_order(4,4,'XUSDT','-1',kind='no_trade_flatten')]
    run['fills']=[u5_fill(1,0,0,'BTCUSDT','1'),u5_fill(2,0,0,'XUSDT','1'),
        u5_fill(3,2,4,'BTCUSDT','-1'),u5_fill(4,4,4,'XUSDT','-1')]
    run['steps']=[u5_step(0)]+[u5_step(h,{'BTCUSDT':'1','XUSDT':'1'}) for h in (1,2,4)]+[u5_step(5),u5_step(6)]
    report=series.recompute(path,run)
    assert report['recompute_passed'],report['differences']
    assert report['max_difference']=='0'


def test_fix2_04_u5_rejected_batch_emits_no_voided_leg(tmp_path):
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0],'XUSDT':[-1,0]},hours=2,
        decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'0.05'},'XUSDT':{'quantity':'1100'}}}])
    run.update(status='failed',failure_reason='gross_exposure_cap',failure_t=START)
    report=series.recompute(path,run)
    assert report['differences']==[]
    assert report['counts']=={'orders':0,'fills':0,'voided':0,'funding':0,'endpoint_funding':0,'steps':0}


@pytest.mark.parametrize('quantity', ['1.05', '-1.05', '1', '-1'])
def test_recorder_quantity_targets_match_u5_step_rounding(tmp_path, quantity):
    path=write_materialization(tmp_path)
    # U5 形狀的觀測值由手算寫定；不以 U6 replay 產生觀測輸出。
    run=observed_fixed_run(path)
    run['decisions'][0]['targets']['BTCUSDT']['quantity']=quantity
    if quantity.startswith('-'):
        run['orders']=[u5_order(1,0,'BTCUSDT','-1'),
            u5_order(2,4,'BTCUSDT','1',kind='score_end_liquidation')]
        run['fills']=[u5_fill(1,0,0,'BTCUSDT','-1',price='99.9',bps='10',fee='0.054945'),
            u5_fill(2,4,4,'BTCUSDT','1',kind='score_end_liquidation',
                    price='100.6',bps='60',fee='0.05533')]
        run['steps']=[u5_step(h) for h in range(-13*24+1,1)]
        run['steps'] += [u5_step(h,{'BTCUSDT':'-1'},cash='99999.945055',
                               equity='99999.845055') for h in (1,2,3)]
        run['steps'] += [u5_step(4,cash='99999.189725')]
        run['funding']=[{'t':START,'symbol':'BTCUSDT','q_before':'0','q_after':'-1',
                        'price':'100','rate':'0','amount':'0','estimated':False}]
    report=series.recompute(path,run)
    assert report['recompute_passed'],report['differences']
    assert report['max_difference']=='0'
    assert report['counts']['orders']==2


@pytest.mark.parametrize('entry,exit_price,crossing', [
    ('85','115','150'), ('99','101','10'), ('80','120',None)])
def test_recorder_stress_breakeven_search_covers_valid_range(tmp_path, entry, exit_price, crossing):
    # 兩筆固定數量成交、零手續費、10 bps 基礎滑價；獨立手算淨損益：
    # 85 -> 115: 30 - 0.2*m，根為 150（128 與 10000/60 之間）。
    # 99 -> 101: 2 - 0.2*m，根為 10；80 -> 120 的根為 200，在有效範圍外。
    bars=[]
    for t in range(START-13*DAY,START+4*HOUR,HOUR):
        price=exit_price if t>=START+2*HOUR else entry
        bars.append([t,price,price,price,price,'10000','10000000'])
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}},
        {'t':START+2*HOUR,'targets':{'BTCUSDT':{'quantity':'0'}}}])
    run['run_config']['cost']['taker_fee_rate']='0'
    refresh_run_hashes(run)
    result=series.stress(path,run)['breakeven']
    if crossing is None:
        assert result['status']=='no_crossing_in_valid_slippage_range'
    else:
        assert result['status']=='bracketed'
        lower,upper=Decimal(result['lower']),Decimal(result['upper'])
        assert lower<Decimal(crossing)<=upper
        assert upper-lower<Decimal('0.000000001')
        assert Decimal(result['lower_net_return'])>0
        assert Decimal(result['upper_net_return'])<=0


@pytest.mark.parametrize('raw_rate', ['1e-05', '-1.2E-4'])
@pytest.mark.parametrize('raw_price', ['100', '1.01e-4'])
def test_sci_source_funding_and_small_prices_match_manual_u5_record(tmp_path, raw_rate, raw_price):
    from decimal import localcontext
    bars=[[t,raw_price,raw_price,raw_price,raw_price,'10000','10000000']
          for t in range(START-13*DAY,START+4*HOUR,HOUR)]
    days=[[t,raw_price,raw_price,raw_price,raw_price,'1000000','20000000']
          for t in range(START-13*DAY,START,DAY)]
    funds=[[t,raw_rate if t==START+HOUR else '0']
           for t in range(START-13*DAY,START+4*HOUR+1,HOUR)]
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars},
        daily={'BTCUSDT':days},funding={'BTCUSDT':funds})
    run=observed_fixed_run(path)
    # 觀測值以 U5 形狀與 Decimal 手算構造；不呼叫 U6 replay／成交／資金費函式。
    with localcontext() as ctx:
        ctx.prec=50
        price,rate=Decimal(raw_price),Decimal(raw_rate)
        entry,exit_price=price*Decimal('1.001'),price*Decimal('0.994')
        entry_fee,exit_fee=entry*Decimal('0.00055'),exit_price*Decimal('0.00055')
        amount=-price*rate*(Decimal('1.02') if rate>0 else Decimal('0.98'))
        cash=Decimal('100000')-entry_fee
        final=cash+amount+exit_price-entry-exit_fee
        text=lambda value:format(value,'f')
        run['fills']=[u5_fill(1,0,0,'BTCUSDT','1',price=text(entry),bps='10',fee=text(entry_fee)),
            u5_fill(2,4,4,'BTCUSDT','-1',kind='score_end_liquidation',
                    price=text(exit_price),bps='60',fee=text(exit_fee))]
        run['steps']=[u5_step(h) for h in range(-13*24+1,1)]
        run['steps'] += [u5_step(h,{'BTCUSDT':'1'},cash=text(cash+(amount if h>=2 else 0)),
            equity=text(cash+(amount if h>=2 else 0)+price-entry)) for h in (1,2,3)]
        run['steps'].append(u5_step(4,cash=text(final)))
        run['funding']=[{'t':START+h*HOUR,'symbol':'BTCUSDT',
            'q_before':'0' if h==0 else '1','q_after':'1','price':text(price),
            'rate':text(rate) if h==1 else '0','amount':text(amount) if h==1 else '0',
            'estimated':False} for h in range(4)]
        run['endpoint_funding']=[{'t':START+4*HOUR,'symbol':'BTCUSDT','q_before':'1',
            'q_after':'0','price':text(price),'rate':'0','amount':'0','estimated':False}]
    report=series.recompute(path,run)
    assert report['recompute_passed'],report['differences']
    assert report['max_difference']=='0'
    assert Decimal(report['totals']['funding']['expected'])==amount
    assert Decimal(run['steps'][-1]['cash'])==final


def replace_source_numbers(path, name, **values):
    source=path.parent/'source'/name
    reader=csv.DictReader(io.StringIO(source.read_text()));fields=reader.fieldnames
    rows=list(reader)
    if not rows:
        rows=[{'timestamp':str(START),**values}]
    else:
        for row in rows:row.update(values)
    buf=io.StringIO(newline='');writer=csv.DictWriter(buf,fieldnames=fields)
    writer.writeheader();writer.writerows(rows);raw=buf.getvalue().encode();source.write_bytes(raw)
    m=json.loads(path.read_bytes());meta=m['files']['source/'+name]
    meta.update(sha256=hashlib.sha256(raw).hexdigest(),rows=len(rows),
                first=int(rows[0]['timestamp']),last=int(rows[-1]['timestamp']))
    path.write_bytes(canonical(m))


def test_sci_source_volume_turnover_and_open_interest(tmp_path):
    path=write_materialization(tmp_path)
    replace_source_numbers(path,'kline_BTCUSDT_60.csv',volume='1.234567890123456789e+4',turnover='1E7')
    replace_source_numbers(path,'kline_BTCUSDT_D.csv',volume='1E6',turnover='2e7')
    replace_source_numbers(path,'open_interest_BTCUSDT_4h.csv',open_interest='1.234567890123456789E-7')
    data=historical_materialization(path)
    assert data.hourly['BTCUSDT'][START]['volume']==Decimal('12345.67890123456789')
    assert data.daily['BTCUSDT'][START-DAY]['volume']==Decimal('1000000')
    assert data.liquidity('BTCUSDT',START,cost_parameters())==(Decimal('20000000'),Decimal('10000000'),True)
    assert series.recompute(path,observed_fixed_run(path))['recompute_passed']


def test_sci_instrument_properties_stay_exact(tmp_path):
    path=write_materialization(tmp_path)
    overlay=path.parent/'symbol_properties_overlay.csv'
    overlay.write_text('bybit,BTCUSDT,cryptofuture,BTCUSDT,USDT,1,1e-8,1e-1,BTCUSDT,1E-1,\n')
    m=json.loads(path.read_bytes());m['symbol_properties_overlay_sha256']=hashlib.sha256(overlay.read_bytes()).hexdigest()
    m['min_notional']['BTCUSDT']='5e-4';path.write_bytes(canonical(m))
    data=historical_materialization(path)
    assert data.properties['BTCUSDT']=={'tick_size':Decimal('0.00000001'),
        'qty_step':Decimal('0.1'),'min_qty':Decimal('0.1'),'min_notional':Decimal('0.0005')}
    assert series.recompute(path,observed_fixed_run(path))['recompute_passed']


@pytest.mark.parametrize('value', ['nan', 'inf', '-Infinity', 'bad', '1e'])
@pytest.mark.parametrize('source', ['funding', 'price', 'open_interest', 'min_notional'])
def test_sci_exchange_fields_reject_nonfinite_and_invalid(tmp_path, source, value):
    path=write_materialization(tmp_path)
    if source=='min_notional':
        m=json.loads(path.read_bytes());m['min_notional']['BTCUSDT']=value;path.write_bytes(canonical(m))
    else:
        name,field={'funding':('funding_BTCUSDT_funding.csv','funding_rate'),
            'price':('kline_BTCUSDT_60.csv','open'),
            'open_interest':('open_interest_BTCUSDT_4h.csv','open_interest')}[source]
        replace_source_numbers(path,name,**{field:value})
    with pytest.raises(series.SeriesError):historical_materialization(path)


@pytest.mark.parametrize('field', ['initial_cash','cost','quantity','weight'])
def test_sci_config_and_targets_remain_strict(tmp_path, field):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    if field=='initial_cash':run['run_config']['initial_cash']='1e5'
    elif field=='cost':run['run_config']['cost']['taker_fee_rate']='5.5e-4'
    else:run['decisions'][0]['targets']['BTCUSDT']={field:'1e0'}
    refresh_run_hashes(run)
    with pytest.raises(series.SeriesError,match='科學記號'):series.recompute(path,run)


@pytest.mark.parametrize('section,field,value', [
    ('fills','price','1.001e2'),('funding','rate','0e0'),('steps','cash','1e5')])
def test_sci_observed_run_numbers_remain_strict(tmp_path, section, field, value):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run[section][0][field]=value
    report=series.recompute(path,run)
    assert not report['recompute_passed']
    assert section+'.0.'+field+':decimal' in report['differences']


# §16：觀測值沿用手寫的 U5-shaped record；不以 replay/recompute 的輸出製造觀測值。
@pytest.mark.parametrize('residual,passed,ulps', [
    (Decimal('0'), True, '0'),
    (Decimal('1e-21'), True, '100'),
    (Decimal('1.01e-21'), False, '101'),
    (Decimal('-1e-21'), True, '100'),
    (Decimal('-1.01e-21'), False, '101'),
], ids=['zero', 'exactly_100_ulp', '101_ulp', 'negative_100_ulp', 'negative_101_ulp'])
def test_fix3_cash_residual_boundary(tmp_path, residual, passed, ulps):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    # 此步 cash=99999.944945，e=4；ulp=10^(4-27)=1e-23，100 ulp=1e-21。
    ulp=Decimal('1e-23');limit=Decimal('1e-21')
    assert limit == 100*ulp
    assert (abs(residual)<=limit) is passed
    t=START+HOUR
    run['unexplained_cash_residual']={
        'per_step':[{'t':t,'residual':format(residual,'f')}] if residual else [],
        'total':format(residual,'f')}
    before=copy.deepcopy(run)
    report=series.recompute(path,run)
    assert report['recompute_passed'] is passed
    assert report['differences'] == ([] if passed else ['unexplained_cash_residual'])
    assert report['max_cash_residual_ulps'] == ulps
    assert report['first_unexplained_cash_residual_t'] == (None if passed else t)
    assert run == before


@pytest.mark.parametrize('residual,passed,ulps', [
    (Decimal('1e-21'), True, '100'),
    (Decimal('1.01e-21'), False, '101'),
])
def test_fix3_end_residual_uses_last_recorded_step_cash(tmp_path, residual, passed, ulps):
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0]},hours=4)
    # 最後一步是 hour 1（end=hour 4 無 step）；記錄 cash<1e5，e=4。
    # initial/replay cash=100000 的 e=5 不能取代它。差 1e-23 在 §9.8.8 內。
    last_cash='99999.9999999999999999999999999'
    run['steps']=[u5_step(0),u5_step(1,cash=last_cash)]
    ulp=Decimal('1e-23');limit=Decimal('1e-21')
    assert limit == 100*ulp
    assert (abs(residual)<=limit) is passed
    t=START+4*HOUR
    run['unexplained_cash_residual']={
        'per_step':[{'t':t,'residual':format(residual,'f')}], 'total':format(residual,'f')}
    report=series.recompute(path,run)
    assert report['recompute_passed'] is passed
    assert report['differences'] == ([] if passed else ['unexplained_cash_residual'])
    assert report['max_cash_residual_ulps'] == ulps
    assert report['first_unexplained_cash_residual_t'] == (None if passed else t)


@pytest.mark.parametrize('cash,initial,ulp,limit,passed,ulps', [
    ('99999.9999999999999999999999999', '100000', Decimal('1e-23'), Decimal('1e-21'), False, '101'),
    ('100000', '99999.9999999999999999999999999', Decimal('1e-22'), Decimal('1e-20'), True, '10.1'),
], ids=['below_100000', 'at_100000'])
def test_fix3_cash_magnitude_uses_recorded_adjusted_exponent(tmp_path,cash,initial,ulp,limit,passed,ulps):
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0]},hours=1)
    run['run_config']['initial_cash']=initial;refresh_run_hashes(run)
    run['steps']=[u5_step(0,cash=cash),u5_step(1,cash=cash)]
    # e=4 -> 1e-23 ulp；e=5 -> 1e-22 ulp。同一殘差分別為 101 與 10.1 ulp。
    # 記錄／重播值分處 1e5 兩側，相差 1e-23，仍在既有現金比較容差內。
    residual=Decimal('1.01e-21')
    assert limit == 100*ulp
    assert (residual<=limit) is passed
    run['unexplained_cash_residual']={
        'per_step':[{'t':START,'residual':format(residual,'f')}], 'total':format(residual,'f')}
    report=series.recompute(path,run)
    assert report['recompute_passed'] is passed
    assert report['differences'] == ([] if passed else ['unexplained_cash_residual'])
    assert report['max_cash_residual_ulps'] == ulps


@pytest.mark.parametrize('residual,passed,ulps', [
    (Decimal('1e-26'), True, '100'),
    (Decimal('1.01e-26'), False, '101'),
    (Decimal('-1e-26'), True, '100'),
])
def test_fix3_zero_cash_uses_decimal_floor(tmp_path,residual,passed,ulps):
    path,run=u5_case(tmp_path,{'BTCUSDT':[-1,0,1,2,3]},hours=4,
        decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}],
        funding={'BTCUSDT':[[START,'1000']]})
    run['run_config']['cost']['funding_delta']='0';refresh_run_hashes(run)
    # 人工帳務：初始 100000，1 BTC x 100 x 1000 資金費 = -100000，現金歸零。
    run['orders']=[u5_order(1,0,'BTCUSDT','1'),u5_order(2,4,'BTCUSDT','-1',kind='score_end_liquidation')]
    run['fills']=[u5_fill(1,0,0,'BTCUSDT','1'),u5_fill(2,4,4,'BTCUSDT','-1',kind='score_end_liquidation')]
    run['funding']=[{'t':START,'symbol':'BTCUSDT','q_before':'0','q_after':'1','price':'100',
                    'rate':'1000','amount':'-100000','estimated':False}]
    run['steps']=[u5_step(0)]+[u5_step(h,{'BTCUSDT':'1'},cash='0') for h in (1,2,3)]+[u5_step(4,cash='0')]
    # cash=0 特例：ulp=1e-28（不是 adjusted(0)-27 的 1e-27）；100 ulp=1e-26。
    ulp=Decimal('1e-28');limit=Decimal('1e-26')
    assert limit == 100*ulp
    assert (abs(residual)<=limit) is passed
    t=START+HOUR
    run['unexplained_cash_residual']={
        'per_step':[{'t':t,'residual':format(residual,'f')}], 'total':format(residual,'f')}
    report=series.recompute(path,run)
    assert report['recompute_passed'] is passed
    assert report['differences'] == ([] if passed else ['unexplained_cash_residual'])
    assert report['max_cash_residual_ulps'] == ulps


@pytest.mark.parametrize('failed', [False,True], ids=['completed', 'u5_failed_at_first_unexplained'])
def test_fix3_first_unexplained_follows_representation_errors(tmp_path,failed):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    # 起始 cash=100000：100 ulp=1e-20；之後 cash=99999.944945：100 ulp=1e-21。
    # 第一筆絕對金額最大（1e-20）但僅 100 ulp；第三筆才是 101 ulp。
    high_limit=Decimal('1e-20');low_limit=Decimal('1e-21');unexplained=Decimal('1.01e-21')
    assert high_limit == 100*Decimal('1e-22')
    assert low_limit == 100*Decimal('1e-23') < unexplained
    first=START+3*HOUR
    run['unexplained_cash_residual']={'per_step':[
        {'t':START,'residual':format(high_limit,'f')},
        {'t':START+HOUR,'residual':format(-low_limit,'f')},
        {'t':first,'residual':format(unexplained,'f')},
        {'t':START+4*HOUR,'residual':format(Decimal('1e-23'),'f')}],
        'total':format(Decimal('1.002e-20'),'f')}
    if failed:
        run.update(status='failed',failure_reason='lean_error',failure_t=first)
    before=copy.deepcopy(run)
    report=series.recompute(path,run)
    assert report['recompute_passed'] is False
    assert report['differences'] == ['unexplained_cash_residual']
    assert report['first_unexplained_cash_residual_t'] == first
    assert report['max_cash_residual_ulps'] == '101'
    assert run == before


def test_fix3_representation_errors_total_does_not_become_a_boundary(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    # 4 筆（最後同時刻含 end callback）各 100 ulp，total=400 ulp 也不構成失敗。
    limit=Decimal('1e-21')
    assert limit == 100*Decimal('1e-23')
    run['unexplained_cash_residual']={'per_step':[
        {'t':START+h*HOUR,'residual':format(limit,'f')} for h in (1,2,4,4)],
        'total':format(Decimal('4e-21'),'f')}
    before=copy.deepcopy(run)
    report=series.recompute(path,run)
    assert report['recompute_passed'] is True
    assert report['differences'] == []
    assert report['max_cash_residual_ulps'] == '100'
    assert report['first_unexplained_cash_residual_t'] is None
    assert run == before

# DV6 固定規格物化；只代表 isolated contract fixture，非 DV2／DV5 真實互通。
def dv6_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def dv6_write(path, name, value, *, jsonl=False, times=()):
    m=json.loads(path.read_bytes());raw=b''.join(dv6_json(v) for v in value) if jsonl else dv6_json(value)
    target=path.parent/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    m['files'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(value) if jsonl else 1,
        'first':min(times) if times else None,'last':max(times) if times else None,
        'source_file':'manifest.json','source_sha256':m['u1_manifest_sha256']}
    path.write_bytes(canonical(m))


def dv6_fixture(tmp_path, *, original='9900000', effective='9900000', hourly='500000',
                md='9900000', me='9900000', mh='12000000', td='GE_1M', te='GE_1M', th='GE_10M',
                triggered=True, selected='hourly_sum', median='12000000', tier='GE_10M', version=2):
    originals=original if isinstance(original,list) else [original]*12
    effectives=effective if isinstance(effective,list) else [effective]*12
    days=list(range(START-12*DAY,START,DAY))
    bars=[[t,'100','100','100','100','10000',hourly] for t in range(START-13*DAY,START+4*HOUR,HOUR)]
    daily=[[t,'100','100','100','100','1000000',v] for t,v in zip(days,effectives) if v is not None]
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars},daily={'BTCUSDT':daily})
    m=json.loads(path.read_bytes());m['readable']=dv6_access()
    raw='timestamp,open,high,low,close,volume,turnover\n'+''.join(
        f'{t},100,100,100,100,1000000,{v}\n' for t,v in zip(days,originals) if v is not None)
    name='verification/original/kline_BTCUSDT_D.csv';target=path.parent/name;target.parent.mkdir(parents=True);target.write_text(raw)
    m['files'][name]={'sha256':hashlib.sha256(raw.encode()).hexdigest(),'rows':sum(v is not None for v in originals),
        'first':days[0],'last':days[-1],'source_file':'kline_BTCUSDT_D.csv.gz','source_sha256':'b'*64}
    path.write_bytes(canonical(m))
    policy={'schema_version':f'r8_data_verification_policy_v{version}','standard_sha256':'afcb87578676c998b4ce7529c6e1c09d5214cfe7e8af53ad03d120781c696931',
        'approval_event':'RH-20261022-05' if version==2 else 'RH-20261022-04','p3b_manifest_sha256':'a'*64,
        'listing':{'x_pct':'50','y_pct':'20','z_pct':'20','cooling_days':7,'quantity':'hourly_base_volume_daily_mean',
                   'variation':'mean_relative_difference','stage_end_ranges':[[1,3],[7,15],[15,30]]},
        'sampling':{'seed':20261022,'base_per_stratum':300,'max_per_stratum':900,'max_expansions':1,'confidence':'0.95','upper_limit':'0.025'},
        'turnover':{'window_days':12,'thresholds':['1000000','10000000','100000000'],'trigger_pct':'5',
                    'general':'exchange_reported','suspect':'sum_hourly_reported'},'l4_price_threshold_pct':'1'}
    if version==2:policy['volume_semantics_policy']='v2-terminal-suffix-20261022'
    dv6_write(path,'verification/policy.json',policy);ph=hashlib.sha256(dv6_json(policy)).hexdigest()
    dv6_write(path,'verification/hypothesis_binding.json',{'schema_version':'r8_verification_hypothesis_binding_v1',
        'hypothesis_id':'h1','policy_sha256':ph,'family':'ordinary','registration_sha256':'e'*64})
    for name in ('corrections','findings','listing_regimes')+ (('volume_semantics',) if version==2 else ()):
        dv6_write(path,'verification/'+name+'.jsonl',[],jsonl=True)
    report={'schema_version':f'r8_data_verification_v{version}','status':'READY','policy_sha256':ph,
        'p3b_manifest_sha256':'a'*64,'sample_plan_sha256':None,'previous_corrections_sha256':None,'review_refs':[],
        'tool_commit':'c'*40,'readable':{'start':START-13*DAY,'end':START+4*HOUR},'counts':dict(input_rows=12,checked_days=12,flagged_days=0,corrected_fields=0,unresolved_rows=0),
        'files':{n: {'sha256':meta['sha256'],'rows':meta['rows']} for n,meta in json.loads(path.read_bytes())['files'].items()
                 if n in ('verification/policy.json','verification/corrections.jsonl','verification/findings.jsonl','verification/volume_semantics.jsonl')},'reason_codes':[]}
    report['files']={k.removeprefix('verification/'):v for k,v in report['files'].items()}
    if version==2:report.update(standard_sha256=policy['standard_sha256'],volume_semantics_policy=policy['volume_semantics_policy'])
    dv6_write(path,'verification/verification.json',report)
    refs=[{'kind':'csv','relative_path':'kline_BTCUSDT_D.csv.gz','sha256':'b'*64,'row':i+2,
           **dict.fromkeys(('url','request_id','list_index','byte_start','byte_end','trade_id','line_sha256'))} for i in range(12)]
    row={'schema_version':'r8_turnover_decision_v1','symbol':'BTCUSDT','decision_utc_day':START,'known_at':START,
        'policy_sha256':ph,'history_sufficient':True,'inputs':[
            {'day_start':t,'exchange_reported':o,'effective_reported':e,'sum_hourly_reported':mh if triggered else None,
             'daily_status':'VALID' if e is not None else 'MISSING','hourly_status':'VALID' if triggered else 'NOT_EVALUATED',
             'source_refs':[ref]} for t,o,e,ref in zip(days,originals,effectives,refs)],
        'm_d':md,'m_e':me,'m_h':mh if triggered else None,'tier_d':td,'tier_e':te,'tier_h':th if triggered else None,
        'triggered':triggered,'selected_source':selected,'selected_median':median,'selected_tier':tier,'status':'READY','reason_codes':[]}
    dv6_write(path,'verification/turnover_decisions.jsonl',[row],jsonl=True,times=[START])
    return path,row


def test_dv6_dual_calculation_controls_replay_and_keeps_hourly_order_cap(tmp_path):
    path,row=dv6_fixture(tmp_path)
    data=series.Materialization(path)
    assert data.liquidity('BTCUSDT',START,cost_parameters())==(Decimal('12000000'),Decimal('500000'),True)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    assert series.replay(data,run)['fills'][0]['slippage_bps']=='10'
    run['decisions'][0]['targets']['BTCUSDT']['quantity']='51'
    assert series.replay(data,run)['voided'][0]['reason']=='order_cap'


from program_code.research.tests.test_r8_engine_materialize import real_peer_materialization, real_peer_run


def test_dv6_integration_real_dv2_materialization(real_peer_materialization, record_property):
    from program_code.research.r8_engine import lean_runner
    from program_code.research.r8_engine.lean_algo import rules
    peer = real_peer_materialization
    for family, output in peer['outputs'].items():
        path = output['root']/'materialization.json'
        data = series.Materialization(path)
        binding = lean_runner.verification_bundle(output['root'], output['manifest'])
        assert binding['family'] == family
        assert binding['registration_sha256'] == output['registration_sha256']
        rows = [json.loads(line) for line in (output['root']/'verification/turnover_decisions.jsonl').read_bytes().splitlines()]
        for row in rows:
            symbol, t = row['symbol'], row['decision_utc_day']
            median, hourly, sufficient = data.liquidity(symbol,t,cost_parameters())
            assert sufficient == row['history_sufficient']
            assert median == Decimal(row['selected_median'])
            reason, bps = rules.turnover_liquidity(row,t,data.manifest['first_bar'][symbol],cost_parameters())
            if not sufficient: assert reason == 'insufficient_history'
        record_property('real_peer', json.dumps(dict(version=peer['version'],family=family,
            materialization=str(path),sha256=data.sha256,decisions=len(rows))))


def test_dv6_integration_real_dv5_run_recompute(real_peer_run, record_property):
    result = series.recompute(real_peer_run['materialization'],real_peer_run['run'])
    assert result['recompute_passed'] is True and result['differences'] == []
    record_property('real_recompute',json.dumps(result))


def dv6_table(path, rows):
    dv6_write(path,'verification/turnover_decisions.jsonl',rows,jsonl=True,times=[r['decision_utc_day'] for r in rows])


@pytest.mark.parametrize('change',[
    {'selected_median':'9900000'}, {'selected_tier':'GE_100M'}, {'selected_source':'effective_daily'},
    {'m_d':'9900000.00000000000000000000000000000000000000001'}, {'m_e':'12000000'},
    {'m_h':'11999999'}, {'tier_d':'GE_10M'}, {'tier_e':'NO_OPEN'}, {'tier_h':'NO_OPEN'},
    {'triggered':False}, {'history_sufficient':False}, {'policy_sha256':'f'*64},
    {'known_at':START+HOUR}, {'schema_version':'r8_turnover_decision_v2'}, {'extra':1},
    {'status':'BLOCKED','selected_source':None,'selected_median':None,'selected_tier':None,'reason_codes':['INPUT_BLOCKED']},
    {'reason_codes':['Z','A']}, {'reason_codes':[1]}, {'reason_codes':'BAD'},
])
def test_dv6_rejects_forged_decision_and_blocked(tmp_path,change):
    path,row=dv6_fixture(tmp_path);row.update(change);dv6_table(path,[row])
    with pytest.raises(series.SeriesError):series.Materialization(path)


@pytest.mark.parametrize('change',[
    {'exchange_reported':'1'},{'effective_reported':'1'},{'sum_hourly_reported':'1'},
    {'day_start':START},{'daily_status':'NOT_EVALUATED'},{'hourly_status':'NOT_EVALUATED'},
    {'source_refs':[]},{'source_refs':[{'kind':'csv'}]},
])
def test_dv6_rejects_forged_twelve_day_inputs(tmp_path,change):
    path,row=dv6_fixture(tmp_path);row['inputs'][0].update(change);dv6_table(path,[row])
    with pytest.raises(series.SeriesError):series.Materialization(path)


@pytest.mark.parametrize('amount,tier,bps', [('500000','NO_OPEN',None),('2000000','GE_1M','20'),
    ('20000000','GE_10M','10'),('200000000','GE_100M','5')])
def test_dv6_four_tiers_and_nontriggered_daily_selection(tmp_path,amount,tier,bps):
    path,row=dv6_fixture(tmp_path,original=amount,effective=amount,md=amount,me=amount,
        td=tier,te=tier,triggered=False,selected='effective_daily',median=amount,tier=tier)
    data=series.Materialization(path)
    assert data.liquidity('BTCUSDT',START,cost_parameters())==(Decimal(amount),Decimal('500000'),True)
    legs=series.order_segments('0','1','100','0.1','0',amount,'500000',True,cost_parameters())
    assert legs[0].get('slippage_bps')==bps
    if bps is None:assert legs[0]['reason']=='untradeable'


@pytest.mark.parametrize('threshold',['1000000','10000000','100000000'])
@pytest.mark.parametrize('side',['0.95','1.05'])
def test_dv6_trigger_boundaries_are_inclusive(tmp_path,threshold,side):
    value=str(Decimal(threshold)*Decimal(side));tier={'1000000':'GE_1M','10000000':'GE_10M','100000000':'GE_100M'}[threshold]
    below={'GE_1M':'NO_OPEN','GE_10M':'GE_1M','GE_100M':'GE_10M'}[tier]
    dt=below if side=='0.95' else tier
    path,row=dv6_fixture(tmp_path,original=value,effective=value,md=value,me=value,td=dt,te=dt)
    # 小時和固定 12M，預期由例子直接指定，不呼叫任何選級實作產生預期。
    selected='effective_daily' if dt=='GE_10M' else 'hourly_sum'
    row.update(selected_source=selected,selected_median=value if selected=='effective_daily' else '12000000',
               selected_tier=dt if selected=='effective_daily' else 'GE_10M');dv6_table(path,[row])
    assert series.Materialization(path).liquidity('BTCUSDT',START,cost_parameters())[0]==Decimal(row['selected_median'])


def test_dv6_median_sixth_seventh_missing_zero_and_suspect_effective_source(tmp_path):
    # 排序後原值中位數 9.9M；有效額第6/7是8M/12M，非平均數，未知日只在計算時映射0。
    values=[None,'50000000','12000000','1000000','30000000','8000000','6000000','14000000','4000000','16000000','2000000','18000000']
    path,row=dv6_fixture(tmp_path,effective=values,me='10000000',te='GE_10M',selected='effective_daily',median='10000000')
    row['reason_codes']=['TURNOVER_INPUT_INCOMPLETE'];dv6_table(path,[row])
    data=series.Materialization(path)
    assert data.liquidity('BTCUSDT',START,cost_parameters())[0]==Decimal('10000000')
    assert START-12*DAY not in data.daily['BTCUSDT']


def test_dv6_trigger_uses_effective_not_original_median(tmp_path):
    path,row=dv6_fixture(tmp_path,effective='20000000',me='20000000',te='GE_10M',
        triggered=False,selected='effective_daily',median='20000000')
    assert series.Materialization(path).liquidity('BTCUSDT',START,cost_parameters())[0]==Decimal('20000000')


def test_dv6_history_insufficient_and_listing_visibility_do_not_change_trade_rules(tmp_path):
    path,row=dv6_fixture(tmp_path);m=json.loads(path.read_bytes());m['first_bar']['BTCUSDT']=START-11*DAY
    path.write_bytes(canonical(m));row.update(history_sufficient=False,selected_tier='NO_OPEN')
    row['inputs'][0].update(hourly_status='MISSING',sum_hourly_reported=None)
    row['reason_codes']=['TURNOVER_INPUT_INCOMPLETE'];dv6_table(path,[row])
    median,hourly,enough=series.Materialization(path).liquidity('BTCUSDT',START,cost_parameters())
    assert (median,hourly,enough)==(Decimal('12000000'),Decimal('500000'),False)
    assert series.order_segments('0','1','100','0.1','0',median,hourly,enough,cost_parameters())==[
        {'quantity':'1','reason':'insufficient_history'}]


def test_dv6_same_key_different_content_is_rejected(tmp_path):
    path,row=dv6_fixture(tmp_path);dv6_table(path,[row,{**row,'selected_tier':'GE_100M'}])
    with pytest.raises(series.SeriesError,match='DUPLICATE'):series.Materialization(path)


@pytest.mark.parametrize('name', ['verification/policy.json','verification/hypothesis_binding.json',
    'verification/verification.json','verification/turnover_decisions.jsonl','verification/original/kline_BTCUSDT_D.csv',
    'verification/volume_semantics.jsonl'])
def test_dv6_missing_or_tampered_manifest_bound_evidence_rejected(tmp_path,name):
    path,row=dv6_fixture(tmp_path);target=path.parent/name;target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(series.SeriesError,match='SHA'):series.Materialization(path)


@pytest.mark.parametrize('version',[1,2])
def test_dv6_schema_versions_and_read_boundary(tmp_path,monkeypatch,version):
    path,row=dv6_fixture(tmp_path,version=version);opened=[];read=Path.read_bytes
    def bounded(file):
        assert file.is_relative_to(path.parent)
        name=file.relative_to(path.parent).as_posix();assert not name.startswith(('lean/','custom/'))
        opened.append(name);return read(file)
    monkeypatch.setattr(Path,'read_bytes',bounded)
    assert series.Materialization(path).liquidity('BTCUSDT',START,cost_parameters())[0]==Decimal('12000000')
    assert 'verification/original/kline_BTCUSDT_D.csv' in opened


def test_dv6_sources_are_checked_before_out_of_scope_values_are_decoded(tmp_path):
    path,row=dv6_fixture(tmp_path);name='verification/original/kline_BTCUSDT_D.csv'
    target=path.parent/name;raw=target.read_bytes().replace(str(START-12*DAY).encode(),str(START+DAY).encode(),1)
    raw=raw.replace(b'9900000',b'not-a-market-value',1);target.write_bytes(raw)
    m=json.loads(path.read_bytes());m['files'][name]['sha256']=hashlib.sha256(raw).hexdigest();path.write_bytes(canonical(m))
    with pytest.raises(series.SeriesError,match='SCOPE'):series.Materialization(path)


def test_dv6_missing_decision_and_policy_window_are_not_silently_legacy(tmp_path):
    path,row=dv6_fixture(tmp_path);data=series.Materialization(path)
    with pytest.raises(series.SeriesError,match='MISSING'):data.liquidity('BTCUSDT',START+DAY,cost_parameters())
    with pytest.raises(series.SeriesError,match='POLICY'):data.liquidity('BTCUSDT',START,{**cost_parameters(),'liquidity_window_days':11})


def dv6_access():
    return {'generation':1,'time_splits':[{'id':'train','kind':'train','start':START-13*DAY,'end':START},
        {'id':'oos','kind':'out_of_sample','start':START,'end':START+4*HOUR},
        {'id':'holdout','kind':'holdout','start':START+DAY,'end':START+2*DAY}],
        'selection':{'symbols':['BTCUSDT']},'out_of_sample':{'start':START-13*DAY,'end':START+4*HOUR},
        'max_lookback_seconds':13*86400,'holdout':None}


def test_dv6_preserves_real_u4_readable_access_shape(tmp_path):
    path,row=dv6_fixture(tmp_path);m=json.loads(path.read_bytes());m['readable']=dv6_access();path.write_bytes(canonical(m))
    assert series.Materialization(path).liquidity('BTCUSDT',START,cost_parameters())[0]==Decimal('12000000')


def dv6_csv(path,name,change):
    target=path.parent/name;reader=csv.DictReader(io.StringIO(target.read_text()));fields=reader.fieldnames
    rows=change(list(reader));buf=io.StringIO(newline='');writer=csv.DictWriter(buf,fieldnames=fields,lineterminator='\n')
    writer.writeheader();writer.writerows(rows);raw=buf.getvalue().encode();target.write_bytes(raw)
    m=json.loads(path.read_bytes());times=[int(r['timestamp']) for r in rows]
    m['files'][name].update(sha256=hashlib.sha256(raw).hexdigest(),rows=len(rows),first=min(times) if times else None,last=max(times) if times else None)
    path.write_bytes(canonical(m))


def test_dv6_incomplete_hourly_days_are_zero_not_partial_or_daily_fallback(tmp_path):
    path,row=dv6_fixture(tmp_path)
    absent={START-i*DAY for i in range(6,13)}
    dv6_csv(path,'source/kline_BTCUSDT_60.csv',lambda rows:[r for r in rows if int(r['timestamp']) not in absent])
    for item in row['inputs']:
        if item['day_start'] in absent:item.update(hourly_status='MISSING',sum_hourly_reported=None)
    row.update(m_h='0',tier_h='NO_OPEN',selected_median='0',selected_tier='NO_OPEN',reason_codes=['TURNOVER_INPUT_INCOMPLETE'])
    dv6_table(path,[row]);data=series.Materialization(path)
    assert data.liquidity('BTCUSDT',START,cost_parameters())==(Decimal('0'),Decimal('500000'),True)
    row['reason_codes']=[];dv6_table(path,[row])
    with pytest.raises(series.SeriesError,match='REASON'):series.Materialization(path)


def test_dv6_original_and_effective_keep_same_p3b_identity(tmp_path):
    path,row=dv6_fixture(tmp_path);m=json.loads(path.read_bytes())
    m['files']['verification/original/kline_BTCUSDT_D.csv']['source_sha256']='f'*64
    path.write_bytes(canonical(m))
    with pytest.raises(series.SeriesError,match='IDENTITY'):series.Materialization(path)


def test_dv6_fixed_independent_run_recomputes_without_u5_helpers(tmp_path):
    path,row=dv6_fixture(tmp_path);run=observed_fixed_run(path)
    report=series.recompute(path,run)
    assert report['recompute_passed'] is True and report['differences']==[]
    run['fills'][0]['slippage_bps']='20'
    report=series.recompute(path,run)
    assert report['recompute_passed'] is False and report['differences']


@pytest.mark.parametrize('name', ['policy.json','hypothesis_binding.json','verification.json'])
def test_dv6_unknown_evidence_fields_rejected(tmp_path,name):
    path,row=dv6_fixture(tmp_path);value=json.loads((path.parent/'verification'/name).read_bytes());value['surprise']='x'
    dv6_write(path,'verification/'+name,value)
    with pytest.raises(series.SeriesError):series.Materialization(path)


@pytest.mark.parametrize('name,change', [
    ('policy.json',{'volume_semantics_policy':'v1-strict'}),('policy.json',{'standard_sha256':'f'*64}),
    ('hypothesis_binding.json',{'hypothesis_id':'other'}),('hypothesis_binding.json',{'policy_sha256':'f'*64}),
    ('verification.json',{'status':'BLOCKED','reason_codes':['NO_PUBLISH']}),
    ('verification.json',{'volume_semantics_policy':'v1-strict'}),('verification.json',{'policy_sha256':'f'*64}),
    ('verification.json',{'p3b_manifest_sha256':'f'*64}),
])
def test_dv6_policy_binding_and_blocked_bundle_rejected(tmp_path,name,change):
    path,row=dv6_fixture(tmp_path);value=json.loads((path.parent/'verification'/name).read_bytes());value.update(change)
    dv6_write(path,'verification/'+name,value)
    with pytest.raises(series.SeriesError):series.Materialization(path)


def test_dv6_v2_confidence_is_bound_but_not_a_trade_gate(tmp_path):
    path,row=dv6_fixture(tmp_path);before=series.Materialization(path).liquidity('BTCUSDT',START,cost_parameters())
    # U6 不讀信心語義作交易條件；此處僅測不透明 bytes 的身份綁定，不代表 DV7 產物驗收。
    dv6_write(path,'verification/volume_semantics.jsonl',[{'confidence_evidence':{'prefix_hlc':{'status':'CONTRADICTS'}}}],jsonl=True)
    report=json.loads((path.parent/'verification/verification.json').read_bytes());meta=json.loads(path.read_bytes())['files']['verification/volume_semantics.jsonl']
    report['files']['volume_semantics.jsonl']={k:meta[k] for k in ('sha256','rows')};dv6_write(path,'verification/verification.json',report)
    assert series.Materialization(path).liquidity('BTCUSDT',START,cost_parameters())==before


@pytest.mark.parametrize('tamper',['extra_evidence','omitted_source','changed_source','manifest_sha'])
def test_dv6_submit_retains_complete_files_and_manifest_identity(tmp_path,tamper):
    f=submit_fixture(tmp_path);record=f['query_record']
    if tamper=='extra_evidence':record['data_files']['verification/turnover_decisions.jsonl']='f'*64
    elif tamper=='omitted_source':record['data_files'].pop('source/kline_BTCUSDT_D.csv')
    elif tamper=='changed_source':record['data_files']['source/kline_BTCUSDT_D.csv']='f'*64
    else:record['manifest_sha256']='f'*64
    before={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    with pytest.raises(series.SeriesError,match='身份'):f['submit']()
    after={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    assert before==after


def test_dv6_holdout_scope_is_rejected_before_source_value_decode(tmp_path,monkeypatch):
    path,row=dv6_fixture(tmp_path);m=json.loads(path.read_bytes())
    m['readable']['time_splits'][-1].update(start=START-HOUR,end=START+HOUR);path.write_bytes(canonical(m))
    read=Path.read_bytes
    def bounded(file):
        assert 'source' not in file.relative_to(path.parent).parts
        return read(file)
    monkeypatch.setattr(Path,'read_bytes',bounded)
    with pytest.raises(series.SeriesError,match='ACCESS_SCOPE'):series.Materialization(path)


@pytest.mark.parametrize('change',[lambda rows:rows+rows[-1:],lambda rows:[{**rows[0],'timestamp':str(START-13*DAY+1)}]+rows[1:],
    lambda rows:[{**rows[0],'turnover':'NaN'}]+rows[1:]])
def test_dv6_bad_hourly_grid_cannot_be_a_valid_sum(tmp_path,change):
    path,row=dv6_fixture(tmp_path);dv6_csv(path,'source/kline_BTCUSDT_60.csv',change)
    with pytest.raises(series.SeriesError):series.Materialization(path)


@pytest.mark.parametrize('encoding',['duplicate_json_key','bom','no_lf','nan','extra_blank'])
def test_dv6_decision_encoding_is_exact(tmp_path,encoding):
    path,row=dv6_fixture(tmp_path);name='verification/turnover_decisions.jsonl';raw=(path.parent/name).read_bytes()
    if encoding=='duplicate_json_key':raw=raw.replace(b'"known_at":',b'"known_at":0,"known_at":')
    elif encoding=='bom':raw=b'\xef\xbb\xbf'+raw
    elif encoding=='no_lf':raw=raw[:-1]
    elif encoding=='nan':raw=raw.replace(b'"m_d":"9900000"',b'"m_d":NaN')
    else:raw+=b'\n'
    (path.parent/name).write_bytes(raw);m=json.loads(path.read_bytes());m['files'][name]['sha256']=hashlib.sha256(raw).hexdigest();path.write_bytes(canonical(m))
    with pytest.raises(series.SeriesError):series.Materialization(path)


@pytest.mark.parametrize('change',[{'untradeable_below_turnover':'999999'},{'order_cap_fraction':'0.02'},
    {'slippage_tiers_bps':[{'min_turnover':'200000000','bps':'5'},{'min_turnover':'10000000','bps':'10'},{'min_turnover':'1000000','bps':'20'}]}])
def test_dv6_cost_cannot_reinterpret_policy_tiers_or_order_cap(tmp_path,change):
    path,row=dv6_fixture(tmp_path)
    with pytest.raises(series.SeriesError,match='POLICY'):
        series.Materialization(path).liquidity('BTCUSDT',START,{**cost_parameters(),**change})


def test_dv6_trial_binding_matches_real_ledger_registration_field(tmp_path):
    path,row=dv6_fixture(tmp_path);m=json.loads(path.read_bytes());m['purpose']='research';path.write_bytes(canonical(m))
    run=run_for(path);cfg=run['run_config'];data=series.Materialization(path)
    configuration={'strategy_parameters':{'run':{k:cfg[k] for k in series.IDENTITY_RUN_KEYS},'strategy':cfg['strategy']},'cost_model_parameters':cfg['cost']}
    record={'configuration':configuration,'configuration_sha256':hashlib.sha256(canonical(configuration)).hexdigest(),
        'code_commit':cfg['code_commit'],'random_seed':1,'sharpe_frequency':{'seconds':3600,'annualized':False},
        **series.RUNTIME_METADATA,'hypothesis_id':'h1','generation':1,'data_window':m['window'],
        'manifest_sha256':data.sha256,'data_files':{k:v['sha256'] for k,v in m['files'].items()},
        'folds':[],'evaluation_kind':'out_of_sample','preregistration_sha256':'e'*64}
    record['evaluation_kind']='in_sample';record['score_window']=m['window']
    series._verify_identity(data,run,record,'test-ledger')
    record['preregistration_sha256']='f'*64
    with pytest.raises(series.SeriesError,match='登記'):series._verify_identity(data,run,record,'test-ledger')


def test_dv6_exact_source_decimals_are_not_cash_tolerances(tmp_path):
    hourly='500000.'+'0'*59+'1';total='12000000.'+'0'*58+'24'
    path,row=dv6_fixture(tmp_path,original='9.9e6',hourly=hourly,mh=total,median=total)
    assert series.Materialization(path).liquidity('BTCUSDT',START,cost_parameters())[0]==Decimal(total)
    row['selected_median']='12000000';dv6_table(path,[row])
    with pytest.raises(series.SeriesError,match='AMOUNT'):series.Materialization(path)


def test_dv6_review_missing_entire_evidence_set_is_rejected(tmp_path):
    path,row=dv6_fixture(tmp_path);m=json.loads(path.read_bytes())
    m['files']={k:v for k,v in m['files'].items() if not k.startswith('verification/')};path.write_bytes(canonical(m))
    with pytest.raises(series.SeriesError,match='VERIFICATION'):series.Materialization(path)


def test_dv6_review_current_engine_cannot_recompute_stripped_evidence_as_legacy(tmp_path):
    path,row=dv6_fixture(tmp_path,original='20000000',effective='20000000',md='20000000',me='20000000',
        td='GE_10M',te='GE_10M',triggered=False,selected='effective_daily',median='20000000')
    m=json.loads(path.read_bytes());m['files']={k:v for k,v in m['files'].items() if not k.startswith('verification/')}
    path.write_bytes(canonical(m));run=observed_fixed_run(path)
    run['algorithm_files']={'program_code/research/r8_engine/series.py':hashlib.sha256(Path(series.__file__).read_bytes()).hexdigest()}
    with pytest.raises(series.SeriesError,match='VERIFICATION'):series.recompute(path,run)


def test_dv6_review_unbound_source_reference_is_rejected(tmp_path):
    path,row=dv6_fixture(tmp_path);row['inputs'][0]['source_refs'][0].update(relative_path='nonexistent.csv',sha256='f'*64)
    dv6_table(path,[row])
    with pytest.raises(series.SeriesError,match='SOURCE_IDENTITY'):series.Materialization(path)


def test_dv6_review_historical_object_cannot_bypass_current_run_gate(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    data=series.Materialization(path,historical=True)
    run['algorithm_files']={'program_code/research/r8_engine/series.py':hashlib.sha256(Path(series.__file__).read_bytes()).hexdigest()}
    with pytest.raises(series.SeriesError,match='VERIFICATION'):series.recompute(data,run)
    with pytest.raises(series.SeriesError,match='VERIFICATION'):series.replay(data,run)


def test_dv6_review_historical_source_identities_are_frozen_real_blobs():
    root=Path(series.__file__).resolve().parents[3];base='55586c1e919958bcac12437404ed7c164832a7fe';name='program_code/research/r8_engine/series.py'
    if subprocess.run(['git','-C',str(root),'cat-file','-e',base],
                      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        pytest.skip('frozen historical Git objects unavailable in shallow checkout')
    commits=subprocess.run(['git','-C',str(root),'log','--format=%H',base,'--',name],check=True,capture_output=True,text=True).stdout.splitlines()
    shas={hashlib.sha256(subprocess.run(['git','-C',str(root),'show',c+':'+name],check=True,capture_output=True).stdout).hexdigest() for c in commits}
    assert series.HISTORICAL_SERIES_SHAS==shas
    assert hashlib.sha256(Path(series.__file__).read_bytes()).hexdigest() not in shas


def test_dv6_review_new_engine_submit_requires_entire_evidence_before_writes(tmp_path):
    f=submit_fixture(tmp_path);name='program_code/research/r8_engine/series.py';raw=Path(series.__file__).read_bytes()
    (f['repo']/name).write_bytes(raw);f['git']('add',name);f['git']('-c','core.hooksPath=/dev/null','commit','-qm','current DV6 engine')
    sha=f['git']('rev-parse','HEAD');f['git']('update-ref','refs/remotes/origin/main',sha)
    f['run']['run_config'].update(code_commit=sha,engine_commit=sha);f['run']['algorithm_files'][name]=hashlib.sha256(raw).hexdigest()
    refresh_run_hashes(f['run'])
    before={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    with pytest.raises(series.SeriesError,match='VERIFICATION'):f['submit']()
    after={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    assert before==after


def test_historical_source_fixture_without_repository_history(tmp_path, monkeypatch):
    # The hosted research job uses a shallow checkout. No history fetch is allowed.
    monkeypatch.setattr(series, '__file__', str(tmp_path/'missing-history/program_code/research/r8_engine/series.py'))
    root, _, files, _ = synthetic_repo(tmp_path)
    name = 'program_code/research/r8_engine/series.py'
    expected = 'a91e604d52b13bdd6a2acb4f4b706ae78147856d6af2c20ca7528c129639dbe4'
    assert files[name] == expected
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected


def historical_series_source():
    """Exact historical source bytes used only for synthetic provenance fixtures.

    Source: 55586c1e919958bcac12437404ed7c164832a7fe, r8_engine/series.py.
    Encoding: base64.b64encode(zlib.compress(git_blob_bytes, 9)). The fixed digest
    is one of the conductor-reviewed historical U6 identities; no test whitelist
    is added and no producer, peer consumer or source identity is substituted.
    Keeping the blob here makes the existing test work without old Git objects.
    """
    import base64
    import zlib
    raw = zlib.decompress(base64.b64decode(
        'eNrFvXt3FEeWIP6/PkWCz05WSikh0TZuSySzdJvp9m+6ba/BsztTU1unJGVJ1ZSq5KoSoKZ1DhhjxMvCbcAGYQO2sQEDfoMMGJ/T'
        'X2VUJekvf4W9j4jIiMjIUuHu3Z9PN8rKjOeNGzfuO7Zu3fr6Dm/t8ltrZ2+ufXHaezGeqMyUqt7GibNr997/+fHy6srZ9pkv28dv'
        'eK8/662dvNU+c7GzeNF7/Tmvs3hu9eGn658ttU+e+K8jb27durWvrzIzW2+0vFJjarbUaMby93ilGU+05K+J+uy8em4ekI/TpeZ0'
        'tTIuf1bq8ulPzXpNPs+UWtPyuaHab7ZKrUqzVZloqjdz47ON+kTcTN7Mq8dWPDNbrlTjvnKjPuNNllpxqzITe+Kr/B16+O+f6zVZ'
        'ToBGFBOQCr2XagdK1crkK7NxA0ZRr4Xea6+8/vKLxRdf+Z8vy+ff7/7DvxRffzX0qvWJUnWiXmvFh1rcbHmuNtGq16tN2fDBRmm2'
        'yd9mYbYAEvnlVfgZeq/ONeJX683KIfzZJwo26lON0kxxoj4ZDzXiZlxqTEwPNX5drMaTU3FjiP/IdiZKtXqtMoGDf02U/QMV6Ovr'
        'm6iWmk1vb9yoxM09jUa9kfu3UnUupsdgtM+D/2Cl1x+vAEoAIjCerN892XnvMqDK2p3P2ucW166dX7t1v33j3bXv3pKY0TcZlyUI'
        'iwewyRz9m7TZXrrdeedG5/z99jtX25+fbp89unHkm9Ufz7bvvr+68g301X7wzfrnn3Q+OgfoKsH/8+MzG0d/ah8/2/n+3sajjzoX'
        'VjpfX+9cfU90i01Xyl6tDvjUrNQAT2oTouPQyzVbjVA2FIiB4H+NEuCrAYOt0HD7yOP2T8c3ri12PvjSGtzWQPaU6gX6CLxSbZLG'
        '0IiHynPVKiDxxHSu4Q/+c3548IXCQO6fR/9ziB+Df/ZDHS5dhwNjWXvz4erKkfXFO+2vluAlgANWAcDYXnp/7fN323dX1m9+sH7p'
        'qhhgqzGvNRs356otL5IQEOtB3+NDE/FsK4XaXqmJn7oObe2t650LiwpAPNKtgUd4CpX1NeEhDFWaxXKlVmnFuadYhCsnNy6dE/Nq'
        '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'
        '5kT/rGUUvUWRNyjeW3wZ7NzMumIi/bIVBAl+QKaNXwVIH+mnqGi1XmoCSCNaC+c0xchTjcqzIw0B1eZWQfy3GkWANevetOQJdyoi'
        'vlkfspzZUbUCkvkk8ANFVTqXamhrpZYcwkVxLivNTfqcJoRLt6IRxa0Jru/UaIPYppUmgTqjGUUSqREXUHYRdSGsTy1ZYC+gmLfs'
        'M9FpM0p1AasNO3fLrgZIPVyahZNmMnd4q2TJto6amj4xrdDbyi3Bd35YCCxkacab9uLkLTbt2l1LVz7YNeVJC/NP4RatCMrkGe3u'
        'r9QmoT33ebw1u8mtrCTcmm7WgpRO1wYiQQ9seUqp23//yuuvwTL/ageqD4b7Xtz97/Br+7OAZvil7xmPVb+AtNuHt+8YHBke3D7s'
        'dT54Z+3Th+tfH20fP+v97fPtQy+gHr69/BAOio1b73fO3//58ZKQW6WNse/V11767Z7ia3v+UNz3yh8004U/Eg++4Ad9v9299/fF'
        '3b/Z6/i8Az7v+R+vv7Tv34v/8tru3+576ZWXHaV+DaV+s2ff7iJMYi/N6Tn+/ceXXi6+8pu9e177t91YFb+9MKw+hR4/7f5fenvD'
        'fhAmv34FTb/0x92/21N88aXf7dm7D0r6zenS9ud2jG7f8dzz8eSvfvXcc3F5/PlfTz7/6/HJ4dJzk8+WR7bvGB8e+dWO50s7fvVc'
        'PDwyPjExuX378PiO556dfP75Z7dPjvx6+/gOv++111/e99If9xT/CMN4cfe+3dA4Y7KPPElxpg5CrD/qHfYrk/DHb/yapJxiY64a'
        'N/3Q85FJAKrH3wZnnx08MOIvMJr4JBQ5WsBDu1gHrCtiic1aiWtTlVqstVCNSzWzkg4dWW0yxm0Z14BeNqkyVisCRNGwU5mKm62M'
        'imi8BYFsBvftBFfdX6sfrBVLWMMHEbAIDeMAaH78lqaEn3Ba+K0Jp1IV9RtF/Lc2MV+cwbaGoZeFvn/Z/dIfXn9tD+LCYW4FNuTB'
        'UmMSm8DaU416s1mMDwFjMNeIkRTj2wrbQ4pSuvHN7eiXqlP1BkgAM0U2oFARhlcxRg7LXxBSJ/L/wH3lyIaMYj1Tt/9OJuTkbR9L'
        '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'
    ))
    assert hashlib.sha256(raw).hexdigest() == 'a91e604d52b13bdd6a2acb4f4b706ae78147856d6af2c20ca7528c129639dbe4'
    return raw
