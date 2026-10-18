"""§7.4 的離線公開介面案例；數值預期為固定手算案例。"""
import ast
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import sys

import pytest
from program_code.research.r8_ledger import ledger as mod


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError('測試禁止網路')
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr(socket.socket,'connect_ex',denied)
    monkeypatch.setattr(socket,'create_connection',denied)


class Clock:
    def __init__(self): self.at=datetime(2026,10,18,tzinfo=timezone.utc)
    def __call__(self):
        self.at+=timedelta(seconds=1)
        return self.at


@pytest.fixture
def registration():
    return {'hypothesis_id':'h1','generation':1,'family':'carry','economic_mechanism':'合成機制',
        'decision_period':{'unit':'day','value':1},'expected_holding_seconds':86400,
        'expected_turnover':1.0,'pessimistic_cost_ratio':0.5,
        'data_range':{'start':mod.DEFAULT_BOUNDARIES[0],'end':mod.DEFAULT_BOUNDARIES[-1]},
        'time_splits':mod.split_intervals(),'primary_metric':'after_cost_sharpe','candidate_thresholds':{'sharpe':1.0},
        'multiple_testing':{'method':'BH','fdr':0.05,'members':['h1'],'members_sha256':mod.sha256(['h1'])},
        'max_lookback_seconds':86400,'label_period_seconds':86400,'max_holding_seconds':86400,
        'selection':{'type':'time_series','rule':'期初已知合約','known_at_period_start':mod.DEFAULT_BOUNDARIES[0]},
        'previous_no_go':None,'split_rationale':'共用預設切分','sharpe_frequency_seconds':86400,
        'oos_protocol':{'scheme':'expanding','initial_train_seconds':365*86400,'test_seconds':30*86400,
                        'step_seconds':30*86400,'purge_seconds':7*86400,'embargo_seconds':7*86400},
        'baselines':[{'id':'no_trade','kind':'strategy_independent'},{'id':'buy_hold','kind':'strategy_independent'}],
        'falsification_rule':{'degradation_z':1.0}}


def registered(tmp_path, record):
    clock=Clock(); b=mod.ResearchLedger(tmp_path/'book',clock=clock); b.preregister(record)
    return b,clock


def test_ledger_identity_clock_and_old_interface_removal(tmp_path,registration):
    b,clock=registered(tmp_path,registration)
    heads=b.export_heads()
    assert heads['ledger_id']
    assert b.verify_heads(heads)==heads
    other=mod.ResearchLedger(tmp_path/'other',clock=clock)
    with pytest.raises(mod.LedgerError): other.verify_heads(heads)
    for name in ('record_trial','benjamini_hochberg','dsr_inputs'): assert not hasattr(b,name)
    with pytest.raises(TypeError): b.preregister(registration,'2026-01-01T00:00:00Z')
    with pytest.raises(TypeError): b.open_holdout('h1','holdout-1',1,'0'*64)
    row=json.loads((b.out/'preregistrations.jsonl').read_text())
    assert row['payload']['recorded_at']=='2026-10-18T00:00:01Z'
    clock.at-=timedelta(days=1)
    with pytest.raises(mod.LedgerError): b.withdraw_hypothesis('h1','clock rollback')


def test_statistics_fixed_moments_bartlett_and_holding_cap():
    # x=[1,2,3,4]：均值2.5，m2=1.25，樣本變異5/3，m3=0，m4=2.5625。
    # q=1，rho1=.25，fB=1.25，T_eff=3.2；持有期為2期時封頂2。
    s=mod.statistics_from_returns([1,2,3,4],period_seconds=1,independent_seconds=1)
    assert s['sr']==pytest.approx(1.9364916731037085)
    assert s['skewness']==0
    assert s['kurtosis']==pytest.approx(1.64)
    assert s['t_eff']==pytest.approx(3.2)
    assert s['bartlett_factor']==pytest.approx(1.25)
    capped=mod.statistics_from_returns([1,2,3,4],period_seconds=1,independent_seconds=2)
    assert capped['t_eff']==2
    assert mod.statistics_from_returns([1,1,1],period_seconds=1,independent_seconds=1)['sr'] is None
    assert mod.statistics_from_returns([1,2],period_seconds=1,independent_seconds=10)['sr'] is None


def test_period_grid_unaligned_endpoints():
    assert mod.period_grid({'start':'1970-01-01T00:00:01Z','end':'1970-01-01T00:00:11Z'},3)==[3,6]
    assert mod.period_grid({'start':'1970-01-01T00:00:03Z','end':'1970-01-01T00:00:12Z'},3)==[3,6,9]


@pytest.mark.parametrize('scheme',['expanding','rolling'])
def test_walk_forward_fixed_fold_table(scheme):
    r={'time_splits':[{'start':'1970-01-01T00:00:00Z','end':'1970-01-01T00:00:10Z'},
                      {'start':'1970-01-01T00:00:11Z','end':'1970-01-01T00:00:30Z'}],
       'oos_protocol':{'scheme':scheme,'initial_train_seconds':10,'test_seconds':4,'step_seconds':6,'purge_seconds':2,'embargo_seconds':3}}
    f=mod.walk_forward_folds(r)
    assert [x['score_window'] for x in f]==[
        {'start':'1970-01-01T00:00:13Z','end':'1970-01-01T00:00:17Z'},
        {'start':'1970-01-01T00:00:19Z','end':'1970-01-01T00:00:23Z'},
        {'start':'1970-01-01T00:00:25Z','end':'1970-01-01T00:00:29Z'}]
    assert [x['fit_window']['start'] for x in f]==(['1970-01-01T00:00:00Z']*3 if scheme=='expanding' else ['1970-01-01T00:00:00Z','1970-01-01T00:00:06Z','1970-01-01T00:00:12Z'])


def test_cscv_fixed_small_matrices_and_tie_ranks():
    # 所有序列相同：平均名次正好在中點，lambda=0 全部計入 PBO。
    tied={'a':[1,2]*16,'b':[1,2]*16}
    assert mod.cscv_pbo(tied)==1
    # 每塊都有同樣的高低值；b 在任意8塊都以相同風險取得更高均值。
    assert mod.cscv_pbo({'a':[1,2]*16,'b':[3,4]*16})==0
    # 兩序列的前後半互反；任何訓練選中的優勢在互補區間反轉（平手也計入）。
    assert mod.cscv_pbo({'a':[2,3]*8+[-3,-2]*8,'b':[-3,-2]*8+[2,3]*8})==1


def trial_record(registration, trial_id='t1', *, role='primary_oos', kind='out_of_sample'):
    r=registration; folds=mod.walk_forward_folds(r)
    config={'strategy_parameters':{'window':2},'cost_model_parameters':{'fee':.001}}
    window={'start':r['time_splits'][0]['start'],'end':r['time_splits'][1]['end']}
    return {'trial_id':trial_id,'hypothesis_id':r['hypothesis_id'],'generation':r['generation'],'parent_trial_id':None,
        'variant_parameters':{'window':2},'data_window':window,'fit_window':window,
        'score_window':{'start':folds[0]['score_window']['start'],'end':folds[-1]['score_window']['end']},
        'manifest_sha256':'1'*64,'data_files':{'data.csv.gz':'2'*64},'code_commit':'3'*40,
        'cost_model':{'id':'cost','version':'1'},'fill_model':{'id':'fill','version':'1'},
        'configuration':config,'configuration_sha256':mod.sha256(config),
        'engine':{'id':'test','version':'1'},'dependencies':{},'time_semantics':{'known_at':'close','fill_at':'next','simulated_latency_ms':300},
        'random_seed':None,'sharpe_frequency':{'unit':'day','seconds':r['sharpe_frequency_seconds'],'annualized':False},
        'evaluation_kind':kind,'role':role,'folds':folds,'oos_protocol_sha256':mod.sha256(r['oos_protocol'])}


def series_file(tmp_path, periods, values=None, *, frequency=86400, filled=0, name='series.json'):
    if values is None: values=[.009,.011]*(len(periods)//2)+([.009] if len(periods)%2 else [])
    value={'period_seconds':frequency,'filled_periods':filled,'returns':[[t,v] for t,v in zip(periods,values)]}
    raw=mod.canonical(value); path=tmp_path/name; path.write_bytes(raw)
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}


def finish_result(tmp_path,record,clock,*,values=None,status='completed',filled=0):
    periods=sorted({t for f in record['folds'] for t in mod.period_grid(f['score_window'],record['sharpe_frequency']['seconds'])})
    return {'status':status,'returns':series_file(tmp_path,periods,values,filled=filled),
            'baselines':{'buy_hold':series_file(tmp_path,periods,[0.0]*len(periods),name='baseline.json')},
            'result_summary':{'source':'synthetic'},'ended_at':clock.at.isoformat()}


def test_begin_finish_freezes_identity_and_copies_series(tmp_path,registration):
    b,clock=registered(tmp_path,registration); t=trial_record(registration)
    b.begin_trial(t)
    r=finish_result(tmp_path,t,clock); source=Path(r['returns']['path']); raw=source.read_bytes()
    b.finish_trial('t1',r)
    stored=b.out/'series'/(r['returns']['sha256']+'.json')
    assert stored.read_bytes()==raw
    assert 'path' not in (b.out/'trials.jsonl').read_text()
    with pytest.raises(mod.LedgerError): b.finish_trial('t1',r)
    with pytest.raises(mod.LedgerError): b.begin_trial({**t,'trial_id':'t2','role':'exploratory'})
    with pytest.raises(mod.LedgerError): b.preregister({**registration,'hypothesis_id':'h2'})
    result=b.close_generation(1)
    assert result['K']==result['K_generation']==1
    assert result['eligible']==['h1']
    h=result['hypotheses']['h1']
    assert h['sr0']==0 and h['p_value']==0
    assert h['n_v']==1 and h['v']==pytest.approx(1/(h['T_eff']-1))
    assert h['accepted'] and h['eligible']
    assert all(x['psr0']>=.95 for x in h['baseline_excess'].values())
    with pytest.raises(mod.LedgerError): b.close_generation(1)


@pytest.mark.parametrize('values,expected',[([.009,.011],True),([-.011,-.009],False),([-.009,.011],False)])
def test_holdout_exact_candidates_and_computed_falsification(tmp_path,registration,values,expected):
    b,clock=registered(tmp_path,registration); t=trial_record(registration)
    b.begin_trial(t); b.finish_trial('t1',finish_result(tmp_path,t,clock)); settled=b.close_generation(1)
    with pytest.raises(mod.HoldoutDenied): b.open_holdout(1,['t1'])
    with pytest.raises(mod.HoldoutDenied): b.seal_holdout('h1','holdout-2')
    b.seal_holdout('h1','holdout-1')
    with pytest.raises(mod.HoldoutDenied): b.seal_holdout('h1','holdout-1')
    with pytest.raises(mod.HoldoutDenied): b.open_holdout(1,[])
    opened=b.open_holdout(1,['t1'])
    assert opened['candidates_sha256']==mod.sha256(['t1'])
    with pytest.raises(mod.HoldoutDenied): b.open_holdout(1,['t1'])
    h={**t,'trial_id':'holdout','evaluation_kind':'holdout_falsification','role':'exploratory','primary_trial_id':'t1',
       'score_window':opened['intervals']['h1'],'data_window':registration['data_range']}
    h.pop('folds')
    b.begin_trial(h)
    periods=mod.period_grid(h['score_window'],86400)
    returns=[values[i%2] for i in range(len(periods))]
    result=b.finish_trial('holdout',{'status':'completed','returns':series_file(tmp_path,periods,returns),
                                 'result_summary':{'source':'synthetic'},'ended_at':clock.at.isoformat()})
    assert result['passed'] is expected
    assert result['cost_positive'] is (sum(values)>0)
    assert result['same_direction'] is (sum(values)>0)
    assert result['sr_ref']==settled['hypotheses']['h1']['sr']-settled['hypotheses']['h1']['sr0']
    # 逐期交替、T=127；以下固定值由樣本矩與 Bartett q=4 計算，另有短序列手算檢查。
    assert result['not_degraded'] is expected
    with pytest.raises(mod.LedgerError): b.begin_trial({**h,'trial_id':'again'})
    assert b.family_trial_count('carry')==1


def test_empty_holdout_opens_and_blocks_later_registration(tmp_path,registration):
    b,clock=registered(tmp_path,registration); b.withdraw_hypothesis('h1','not pursued')
    result=b.close_generation(1)
    assert result['K']==0 and result['hypotheses']['h1']['p_value']==1
    opened=b.open_holdout(1,[])
    assert opened['intervals']=={} and opened['candidates_sha256']==mod.sha256([])
    r={**registration,'hypothesis_id':'g2','generation':2}
    r['multiple_testing']={'method':'BH','fdr':.05,'members':['g2'],'members_sha256':mod.sha256(['g2'])}
    with pytest.raises(mod.LedgerError): b.preregister(r)


@pytest.mark.parametrize('field',['hypothesis_id','generation','family','economic_mechanism','decision_period','expected_holding_seconds','expected_turnover','pessimistic_cost_ratio','data_range','time_splits','primary_metric','candidate_thresholds','multiple_testing','max_lookback_seconds','label_period_seconds','max_holding_seconds','selection','split_rationale','previous_no_go','sharpe_frequency_seconds','oos_protocol','baselines','falsification_rule'])
def test_preregistration_required_fields(tmp_path,registration,field):
    del registration[field]
    with pytest.raises(mod.LedgerError): registered(tmp_path,registration)


@pytest.mark.parametrize('change',['member_hash','generation','fdr_zero','fdr_half','frequency','label','holding','fast','known_at','protocol_step','protocol_grid','protocol_gap','no_fold','z','no_trade','passive','small_sample'])
def test_preregistration_rejects_invalid_boundaries_and_parameters(tmp_path,registration,change):
    r=registration
    if change=='member_hash': r['multiple_testing']['members_sha256']='f'*64
    elif change=='generation': r['generation']=3
    elif change=='fdr_zero': r['multiple_testing']['fdr']=0
    elif change=='fdr_half': r['multiple_testing']['fdr']=.5
    elif change=='frequency': r['sharpe_frequency_seconds']=True
    elif change=='label': r['label_period_seconds']=1
    elif change=='holding': r['max_holding_seconds']=1
    elif change=='fast': r['decision_period']={'unit':'hour','value':.5}
    elif change=='known_at': r['selection']['known_at_period_start']='2022-01-02T00:00:00Z'
    elif change=='protocol_step': r['oos_protocol']['step_seconds']=86400
    elif change=='protocol_grid': r['oos_protocol']['test_seconds']+=1
    elif change=='protocol_gap': r['oos_protocol']['purge_seconds']=1
    elif change=='no_fold': r['oos_protocol']['initial_train_seconds']=99*365*86400
    elif change=='z': r['falsification_rule']['degradation_z']=.49
    elif change=='no_trade': r['baselines']=r['baselines'][1:]
    elif change=='passive': r['baselines']=r['baselines'][:1]
    elif change=='small_sample': r['oos_protocol']['initial_train_seconds']=1430*86400
    with pytest.raises(mod.LedgerError): registered(tmp_path,r)


@pytest.mark.parametrize('kind',['cross_sectional','filtered'])
@pytest.mark.parametrize('proof',['point_in_time_universe_source','no_delistings_proof'])
def test_selection_evidence_and_no_go_branches(tmp_path,registration,kind,proof):
    registration['selection']={'type':kind,'rule':'fixed'}
    b=mod.ResearchLedger(tmp_path/'book',clock=Clock())
    with pytest.raises(mod.LedgerError): b.preregister(registration)
    registration['selection'][proof]='source-hash'
    registration['previous_no_go']={'decision_ref':'NO-GO-1','differences':'different mechanism'}
    b.preregister(registration)
    with pytest.raises(mod.LedgerError): b.preregister(registration)


@pytest.mark.parametrize('field',['method','fdr','frequency','boundaries','baselines'])
def test_generation_common_contract_cannot_drift(tmp_path,registration,field):
    registration['multiple_testing']['members']=['h1','h2']; registration['multiple_testing']['members_sha256']=mod.sha256(['h1','h2'])
    b,clock=registered(tmp_path,registration); r=copy.deepcopy(registration); r['hypothesis_id']='h2'
    if field=='method': r['multiple_testing']['method']='BY'
    if field=='fdr': r['multiple_testing']['fdr']=.04
    if field=='frequency': r['sharpe_frequency_seconds']=43200
    if field=='boundaries': r['time_splits'][1]['start']='2025-07-09T00:00:00Z'
    if field=='baselines': r['baselines'][1]['kind']='exposure_matched'
    with pytest.raises(mod.LedgerError): b.preregister(r)


@pytest.mark.parametrize('tamper',['bad_link','noncanonical','delete','wrong_hash'])
def test_anchored_chain_integrity_and_prefix_survives_append(tmp_path,registration,tamper):
    b,clock=registered(tmp_path,registration); pinned=b.export_heads()
    b.withdraw_hypothesis('h1','test'); assert b.verify_heads(pinned)['preregistrations']!=pinned['preregistrations']
    path=b.out/'preregistrations.jsonl'; rows=[json.loads(line) for line in path.read_bytes().splitlines()]
    if tamper=='bad_link':
        rows[1]['previous']='a'*64; rows[1]['hash']=mod.sha256({k:rows[1][k] for k in ('sequence','previous','payload')})
    elif tamper=='wrong_hash': rows[0]['payload']['record']['family']='changed'
    elif tamper=='delete': rows=[]
    path.write_bytes(b''.join((json.dumps(row).encode() if tamper=='noncanonical' else mod.canonical(row))+b'\n' for row in rows))
    with pytest.raises(mod.LedgerError): b.verify_heads(pinned)


@pytest.mark.parametrize('field',['trial_id','generation','parent_trial_id','variant_parameters','data_window','manifest_sha256','data_files','code_commit','cost_model','fill_model','configuration','configuration_sha256','engine','dependencies','time_semantics','random_seed','sharpe_frequency','evaluation_kind','fit_window','score_window','folds','oos_protocol_sha256'])
def test_begin_identity_required_fields(tmp_path,registration,field):
    b,clock=registered(tmp_path,registration); t=trial_record(registration); del t[field]
    with pytest.raises(mod.LedgerError): b.begin_trial(t)


@pytest.mark.parametrize('change',['commit','cost_id','data_window','folds','frequency','protocol','sharpe','recorded_at','p_value','passed'])
def test_trial_identity_and_result_fields_rejected(tmp_path,registration,change):
    b,clock=registered(tmp_path,registration); t=trial_record(registration)
    if change=='commit': t['code_commit']='short'
    elif change=='cost_id': del t['cost_model']['id']
    elif change=='data_window': t['data_window']['end']='2027-01-01T00:00:00Z'
    elif change=='folds': t['folds']=t['folds'][:-1]
    elif change=='frequency': t['sharpe_frequency']['seconds']=43200
    elif change=='protocol': t['oos_protocol_sha256']='a'*64
    else: t[change]=1
    with pytest.raises(mod.LedgerError): b.begin_trial(t)


@pytest.mark.parametrize('change',['missing','hash','grid','frequency','nonfinite','noncanonical','early_end','late_end','identity','p_value','no_trade'])
def test_finish_series_and_clock_validation(tmp_path,registration,change):
    b,clock=registered(tmp_path,registration); t=trial_record(registration); b.begin_trial(t)
    r=finish_result(tmp_path,t,clock)
    if change=='missing': del r['returns']
    elif change=='hash': r['returns']['sha256']='f'*64
    elif change in ('grid','frequency','nonfinite','noncanonical'):
        path=Path(r['returns']['path']); value=json.loads(path.read_bytes())
        if change=='grid': value['returns'][0][0]+=1
        if change=='frequency': value['period_seconds']=43200
        if change=='nonfinite': value['returns'][0][1]=float('inf')
        raw=json.dumps(value).encode() if change in ('noncanonical','nonfinite') else mod.canonical(value)
        path.write_bytes(raw); r['returns']['sha256']=hashlib.sha256(raw).hexdigest()
    elif change=='early_end': r['ended_at']='2020-01-01T00:00:00Z'
    elif change=='late_end': r['ended_at']='2030-01-01T00:00:00Z'
    elif change=='identity': r['code_commit']='4'*40
    elif change=='p_value': r['p_value']=0
    elif change=='no_trade': r['baselines']['no_trade']=r['baselines']['buy_hold']
    with pytest.raises(mod.LedgerError): b.finish_trial('t1',r)


@pytest.mark.parametrize('k,expected_p,expected_sr0',[(1,.00051301084146127,0),(10,.04375381002549106,.04793569807324347)])
def test_fixed_k_one_and_ten_dsr_counts_all_statuses(tmp_path,registration,k,expected_p,expected_sr0):
    b,clock=registered(tmp_path,registration)
    for i in range(k-1):
        t=trial_record(registration,'e'+str(i),role='exploratory',kind='in_sample')
        b.begin_trial(t)
        if i%3:
            b.finish_trial(t['trial_id'],{'status':'failed' if i%3==1 else 'aborted','produced_periods':0,'result_summary':{'why':'synthetic'},'ended_at':clock.at.isoformat()})
    t=trial_record(registration); b.begin_trial(t)
    # 36折，每折30日；x=0.1+[-1,1]，SR=0.1*sqrt(1079/1080)，T_eff=1080。
    r=finish_result(tmp_path,t,clock,values=[-.9,1.1]*540); b.finish_trial('t1',r)
    result=b.close_generation(1); h=result['hypotheses']['h1']
    assert h['T']==1080 and h['T_eff']==1080
    assert result['K']==k
    assert h['sr']==pytest.approx(.09995369298200413)
    assert h['sr0']==pytest.approx(expected_sr0)
    assert h['p_value']==pytest.approx(expected_p,abs=1e-12)
    assert h['n_v']==1 and h['v']==pytest.approx(1/1079)
    if k==10:
        assert h['accepted'] and h['pbo'] is None and not h['eligible']
        assert b.pbo_status('h1')=={'required':True,'non_holdout_trial_count':10,'N':1}


def test_fixed_sample_variance_with_two_completed_oos(tmp_path,registration):
    b,clock=registered(tmp_path,registration)
    for tid,role,values in [('e','exploratory',[-.9,1.1]*540),('t1','primary_oos',[-.8,1.2]*540)]:
        t=trial_record(registration,tid,role=role); b.begin_trial(t); b.finish_trial(tid,finish_result(tmp_path,t,clock,values=values))
    h=b.close_generation(1)['hypotheses']['h1']
    # SR差=0.1*sqrt(1079/1080)，兩筆的樣本變異數是差的平方/2。
    assert h['n_v']==2
    assert h['variance_sample']==pytest.approx(.0049953703703703705)
    assert h['v']==pytest.approx(.0049953703703703705)


@pytest.mark.parametrize('method,expected,eligible',[('BH',[.213725337970174,.14699714585687018],['h2']),('BY',[.320588006955261,.22049571878530527],[])])
def test_generation_bh_by_fixed_family_and_adjusted_p(tmp_path,registration,method,expected,eligible):
    registration['multiple_testing']={'method':method,'fdr':.2,'members':['h1','h2'],'members_sha256':mod.sha256(['h1','h2'])}
    b,clock=registered(tmp_path,registration); r2=copy.deepcopy(registration); r2.update(hypothesis_id='h2',family='other-label'); b.preregister(r2)
    for r,mean in [(registration,.04),(r2,.06)]:
        t=trial_record(r,r['hypothesis_id']); b.begin_trial(t)
        b.finish_trial(t['trial_id'],finish_result(tmp_path,t,clock,values=[mean-1,mean+1]*540))
    result=b.close_generation(1)
    assert result['m']==2 and result['members_sha256']==mod.sha256(['h1','h2'])
    assert [result['hypotheses'][h]['adjusted_p_value'] for h in ['h1','h2']]==pytest.approx(expected)
    assert result['eligible']==eligible


def plan_identity(t):
    return {'variant_parameters_sha256':mod.sha256(t['variant_parameters']),
            **{k:t[k] for k in ('evaluation_kind','role','parent_trial_id','data_window','fit_window','score_window')},
            'primary_trial_id':t.get('primary_trial_id')}


def test_second_generation_frozen_plan_cross_family_parent_and_unstarted_k(tmp_path,registration):
    b,clock=registered(tmp_path,registration)
    r2=copy.deepcopy(registration); r2.update(hypothesis_id='g2',generation=2,family='different')
    r2['multiple_testing'].update(members=['g2'],members_sha256=mod.sha256(['g2'])); b.preregister(r2)
    parent=trial_record(registration,'parent',role='exploratory',kind='in_sample'); b.begin_trial(parent)
    p=trial_record(r2,'primary'); p['parent_trial_id']='parent'
    unused=trial_record(r2,'unused',role='exploratory',kind='in_sample'); unused['parent_trial_id']='parent'
    bad=copy.deepcopy(p); bad['parent_trial_id']=None
    with pytest.raises(mod.LedgerError): b.begin_trial(bad)
    b.commit_trial_plan('g2',[plan_identity(p),plan_identity(unused)])
    b.withdraw_hypothesis('h1','not pursued'); result=b.close_generation(1)
    assert result['K']==3 and result['planned_unstarted_count']==2
    b.open_holdout(1,[])
    with pytest.raises(mod.LedgerError): b.commit_trial_plan('g2',[plan_identity(p)])
    changed=copy.deepcopy(p); changed['variant_parameters']['window']=3
    with pytest.raises(mod.LedgerError): b.begin_trial(changed)
    b.begin_trial(p)
    b.finish_trial('primary',{'status':'aborted','produced_periods':0,'result_summary':{'why':'early'},'ended_at':clock.at.isoformat()})
    result=b.close_generation(2)
    assert result['K']==3 and result['K_generation']==2 and result['planned_unstarted_count']==1
    assert result['hypotheses']['g2']['p_value']==1
    assert b.open_holdout(2,[])['intervals']=={}


@pytest.mark.parametrize('status',['failed','aborted'])
def test_failed_oos_requires_existing_returns_but_always_p_one(tmp_path,registration,status):
    b,clock=registered(tmp_path,registration); t=trial_record(registration); b.begin_trial(t)
    result={'status':status,'produced_periods':2,'result_summary':{'why':'failed'},'ended_at':clock.at.isoformat()}
    with pytest.raises(mod.LedgerError): b.finish_trial('t1',result)
    b.finish_trial('t1',finish_result(tmp_path,t,clock,status=status))
    h=b.close_generation(1)['hypotheses']['h1']
    assert h['p_value']==1 and h['p_value_reason']==status and not h['eligible']


@pytest.mark.parametrize('case',['zero','filled'])
def test_invalid_statistics_force_p_one(tmp_path,registration,case):
    b,clock=registered(tmp_path,registration); t=trial_record(registration); b.begin_trial(t)
    result=finish_result(tmp_path,t,clock,values=[.01]*1080 if case=='zero' else None,filled=55 if case=='filled' else 0)
    b.finish_trial('t1',result); h=b.close_generation(1)['hypotheses']['h1']
    assert h['p_value']==1 and not h['accepted']
    assert h['p_value_reason']==('zero_standard_deviation' if case=='zero' else 'excess_filled_periods')


def test_falsification_fixed_numeric_standard_error(tmp_path,registration):
    registration['time_splits'][2]['end']='2026-05-16T00:00:00Z'
    registration['time_splits'][3]['start']='2026-05-23T00:00:00Z'
    b,clock=registered(tmp_path,registration); t=trial_record(registration)
    b.begin_trial(t); b.finish_trial('t1',finish_result(tmp_path,t,clock,values=[-.9,1.1]*540)); b.close_generation(1)
    b.seal_holdout('h1','holdout-1'); opened=b.open_holdout(1,['t1'])
    h={**t,'trial_id':'holdout','evaluation_kind':'holdout_falsification','role':'exploratory','primary_trial_id':'t1',
       'score_window':opened['intervals']['h1'],'data_window':registration['data_range']}; h.pop('folds')
    b.begin_trial(h); periods=mod.period_grid(h['score_window'],86400); assert len(periods)==128
    result=b.finish_trial('holdout',{'status':'completed','returns':series_file(tmp_path,periods,[-.95,1.05]*64),
                                   'result_summary':{'synthetic':True},'ended_at':clock.at.isoformat()})
    # SR_h=.05*sqrt(127/128)，gamma3=0，gamma4=1，SE_h=1/sqrt(127)。
    assert result['sr_h']==pytest.approx(.049804304532841344)
    assert result['se_h']==pytest.approx(.08873565094161139)
    assert result['sr_ref']==pytest.approx(.09995369298200413)
    assert result['t_eff_h']==128 and result['gamma3_h']==pytest.approx(0,abs=1e-14) and result['gamma4_h']==pytest.approx(1)
    assert result['cost_positive'] and result['same_direction'] and result['not_degraded'] and result['passed']


def test_shared_segment_seals_per_hypothesis_and_generation_two_order(tmp_path,registration):
    registration['multiple_testing'].update(members=['h1','h2'],members_sha256=mod.sha256(['h1','h2']))
    b,clock=registered(tmp_path,registration); r=copy.deepcopy(registration); r['hypothesis_id']='h2'; b.preregister(r)
    b.seal_holdout('h1','holdout-1'); b.seal_holdout('h2','holdout-1')
    g2=copy.deepcopy(registration); g2.update(hypothesis_id='g2',generation=2)
    g2['multiple_testing'].update(members=['g2'],members_sha256=mod.sha256(['g2'])); b.preregister(g2)
    b.withdraw_hypothesis('g2','test'); b.close_generation(2)
    with pytest.raises(mod.HoldoutDenied): b.open_holdout(2,[])


def test_computed_sample_warning_and_power_fields(tmp_path,registration):
    registration['max_holding_seconds']=30*86400
    registration['oos_protocol'].update(purge_seconds=30*86400,embargo_seconds=30*86400)
    b,clock=registered(tmp_path,registration)
    record=json.loads((b.out/'preregistrations.jsonl').read_text())['payload']['record']
    assert 30<=record['effective_independent_periods']['out_of_sample']<100
    assert set(record['sample_size_warning'])=={'out_of_sample','holdout-1','holdout-2'}
    assert all(value>0 for value in record['detectable_sharpe'].values())
    assert record['oos_protocol_sha256']==mod.sha256(registration['oos_protocol'])


@pytest.mark.parametrize('matched',[False,True])
def test_baseline_identity_constraint_and_excess_gate(tmp_path,registration,matched):
    if matched: registration['baselines'][1]['kind']='exposure_matched'
    b,clock=registered(tmp_path,registration)
    t=trial_record(registration,'e',role='exploratory'); b.begin_trial(t); b.finish_trial('e',finish_result(tmp_path,t,clock))
    t=trial_record(registration); b.begin_trial(t); r=finish_result(tmp_path,t,clock)
    periods=sorted({p for f in t['folds'] for p in mod.period_grid(f['score_window'],86400)})
    r['baselines']['buy_hold']=series_file(tmp_path,periods,[.1]*len(periods),name='new-baseline.json')
    if not matched:
        with pytest.raises(mod.LedgerError): b.finish_trial('t1',r)
    else:
        b.finish_trial('t1',r); h=b.close_generation(1)['hypotheses']['h1']
        assert h['accepted'] and h['baseline_excess']['buy_hold']['psr0']<.95 and not h['eligible']


def test_stdlib_only_and_python310_ast():
    for path in Path(mod.__file__).parent.glob('*.py'):
        tree=ast.parse(path.read_text(),feature_version=(3,10))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import): assert all(a.name.split('.')[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node,ast.ImportFrom) and not node.level: assert node.module.split('.')[0] in sys.stdlib_module_names
            elif isinstance(node,ast.Call):
                assert not (isinstance(node.func,ast.Name) and node.func.id=='__import__')
                assert not (isinstance(node.func,ast.Attribute) and node.func.attr=='import_module')


@pytest.mark.parametrize('tied,expected_pbo',[(False,0.0),(True,1.0)])
def test_pbo_ten_completed_variants_controls_eligibility(tmp_path,registration,tied,expected_pbo):
    b,clock=registered(tmp_path,registration)
    for i in range(10):
        t=trial_record(registration,'t'+str(i),role='primary_oos' if i==9 else 'exploratory')
        t['variant_parameters']={'window':i}; b.begin_trial(t)
        mean=.01 if tied else .01+i*.001
        b.finish_trial(t['trial_id'],finish_result(tmp_path,t,clock,values=[mean-.001,mean+.001]*540))
        if i==8: assert b.pbo_status('h1')=={'required':False,'non_holdout_trial_count':9,'N':9}
    h=b.close_generation(1)['hypotheses']['h1']
    assert h['accepted'] and h['pbo_required'] and h['pbo_series_count']==10
    assert h['pbo']==expected_pbo
    assert h['eligible'] is (not tied)


def test_cli_new_actions_and_no_caller_write_time(tmp_path,registration,capsys):
    path=tmp_path/'registration.json'; path.write_bytes(mod.canonical(registration)); out=tmp_path/'book'
    mod.main(['--out',str(out),'preregister','--record',str(path)])
    capsys.readouterr()
    mod.main(['--out',str(out),'heads']); heads=json.loads(capsys.readouterr().out)
    assert heads['ledger_id']
    path.write_bytes(mod.canonical({'hypothesis_id':'h1','reason':'not pursued'}))
    mod.main(['--out',str(out),'withdraw_hypothesis','--record',str(path)]); capsys.readouterr()
    path.write_bytes(mod.canonical({'generation':1}))
    mod.main(['--out',str(out),'close_generation','--record',str(path)]); result=json.loads(capsys.readouterr().out)
    assert result['eligible']==[]
    path.write_bytes(mod.canonical({'generation':1,'candidate_trial_ids':[]}))
    mod.main(['--out',str(out),'open_holdout','--record',str(path)])
    assert json.loads(capsys.readouterr().out)['intervals']=={}
    for action in ('trial','record_trial','benjamini_hochberg','dsr_inputs'):
        with pytest.raises(SystemExit): mod.main(['--out',str(out),action,'--record',str(path)])


@pytest.mark.parametrize('field',['recorded_at','registered_at','sharpe','p_value','passed','effective_independent_periods'])
def test_preregister_rejects_caller_statistics_or_clock(tmp_path,registration,field):
    registration[field]=1
    with pytest.raises(mod.LedgerError): registered(tmp_path,registration)


def test_variance_pool_excludes_different_oos_protocol(tmp_path,registration):
    registration['multiple_testing'].update(members=['h1','h2'],members_sha256=mod.sha256(['h1','h2']))
    b,clock=registered(tmp_path,registration); r=copy.deepcopy(registration); r['hypothesis_id']='h2'; r['oos_protocol']['scheme']='rolling'; b.preregister(r)
    for item in (registration,r):
        t=trial_record(item,item['hypothesis_id']); b.begin_trial(t); b.finish_trial(t['trial_id'],finish_result(tmp_path,t,clock))
    result=b.close_generation(1)
    assert all(h['n_v']==1 for h in result['hypotheses'].values())


def test_plan_identity_used_once_and_preregistration_freezes_on_begin(tmp_path,registration):
    b,clock=registered(tmp_path,registration); r=copy.deepcopy(registration); r.update(hypothesis_id='g2',generation=2)
    r['multiple_testing'].update(members=['g2'],members_sha256=mod.sha256(['g2'])); b.preregister(r)
    t=trial_record(registration,'parent',role='exploratory',kind='in_sample'); b.begin_trial(t)
    planned=trial_record(r,'child',role='exploratory',kind='in_sample'); planned['parent_trial_id']='parent'
    b.commit_trial_plan('g2',[plan_identity(planned)])
    b.withdraw_hypothesis('h1','test'); b.close_generation(1); b.open_holdout(1,[])
    b.begin_trial(planned)
    with pytest.raises(mod.LedgerError): b.begin_trial({**planned,'trial_id':'duplicate'})


def test_close_requires_finished_primary_and_all_declared_members(tmp_path,registration):
    b,clock=registered(tmp_path,registration)
    with pytest.raises(mod.LedgerError): b.close_generation(1)
    t=trial_record(registration); b.begin_trial(t)
    with pytest.raises(mod.LedgerError): b.close_generation(1)
    b.withdraw_hypothesis('h1','stop')
    with pytest.raises(mod.LedgerError): b.begin_trial({**t,'trial_id':'next'})
    assert b.close_generation(1)['K']==1
    r=copy.deepcopy(registration); r['multiple_testing'].update(members=['h1','missing'],members_sha256=mod.sha256(['h1','missing']))
    other=mod.ResearchLedger(tmp_path/'other',clock=Clock()); other.preregister(r); other.withdraw_hypothesis('h1','stop')
    with pytest.raises(mod.LedgerError): other.close_generation(1)


def test_holdout_failed_without_series_is_not_passed(tmp_path,registration):
    b,clock=registered(tmp_path,registration); t=trial_record(registration); b.begin_trial(t); b.finish_trial('t1',finish_result(tmp_path,t,clock))
    b.close_generation(1); b.seal_holdout('h1','holdout-1'); opened=b.open_holdout(1,['t1'])
    h={**t,'trial_id':'h','evaluation_kind':'holdout_falsification','role':'exploratory','primary_trial_id':'t1',
       'score_window':opened['intervals']['h1'],'data_window':registration['data_range']}; h.pop('folds')
    wrong={**h,'variant_parameters':{'changed':True}}
    with pytest.raises(mod.LedgerError): b.begin_trial(wrong)
    b.begin_trial(h)
    result=b.finish_trial('h',{'status':'failed','produced_periods':0,'result_summary':{'why':'failed'},'ended_at':clock.at.isoformat()})
    assert not result['passed'] and result['sr_h'] is None


@pytest.mark.parametrize('candidates',[None,'t1',[None],[1],['']])
def test_repeat_holdout_with_invalid_candidates_is_audited(tmp_path,registration,candidates):
    b,_=registered(tmp_path,registration)
    b.withdraw_hypothesis('h1','test'); b.close_generation(1); b.open_holdout(1,[])
    previous=b._events('holdouts')
    with pytest.raises(mod.HoldoutDenied): b.open_holdout(1,candidates)
    events=b._events('holdouts')
    assert events[:-1]==previous and len(events)==len(previous)+1
    assert events[-1]['action']=='denied' and events[-1]['generation']==1
    assert 'intervals' not in events[-1]


def pending_holdout(tmp_path,registration):
    b,clock=registered(tmp_path,registration); t=trial_record(registration)
    b.begin_trial(t); b.finish_trial('t1',finish_result(tmp_path,t,clock)); b.close_generation(1)
    b.seal_holdout('h1','holdout-1'); opened=b.open_holdout(1,['t1'])
    h={**t,'trial_id':'h','evaluation_kind':'holdout_falsification','role':'exploratory','primary_trial_id':'t1',
       'score_window':opened['intervals']['h1'],'data_window':registration['data_range']}; h.pop('folds')
    b.begin_trial(h)
    periods=mod.period_grid(h['score_window'],86400)
    result={'status':'completed','returns':series_file(tmp_path,periods),
            'result_summary':{'source':'synthetic'},'ended_at':clock.at.isoformat()}
    return b,clock,result


@pytest.mark.parametrize('failure',['before_append','after_append','clock_rollback','interrupt'])
def test_holdout_finish_recovers_from_saved_trial_without_source_file(tmp_path,registration,monkeypatch,failure):
    b,clock,result=pending_holdout(tmp_path,registration); append=b._append; saved_time=clock.at
    def fail(name,payload,**kwargs):
        if name=='holdouts' and payload['action']=='falsification_result':
            if failure=='clock_rollback':
                clock.at-=timedelta(days=1)
                return append(name,payload,**kwargs)
            if failure=='after_append': append(name,payload,**kwargs)
            if failure=='interrupt': raise KeyboardInterrupt('simulated interruption')
            raise OSError('simulated write failure')
        return append(name,payload,**kwargs)
    monkeypatch.setattr(b,'_append',fail)
    with pytest.raises((OSError,mod.LedgerError,KeyboardInterrupt)): b.finish_trial('h',result)
    assert b._trials()['h']['finished']
    count=len(b._events('trials')); clock.at=saved_time+timedelta(seconds=10)
    Path(result['returns']['path']).unlink()
    recovered=mod.ResearchLedger(b.out,clock=clock)
    with pytest.raises(mod.LedgerError): recovered.finish_trial('h',{**result,'status':'failed'})
    verdict=recovered.finish_trial('h',result)
    assert verdict['action']=='falsification_result' and verdict['passed']
    assert recovered.finish_trial('h',result)==verdict
    assert len(recovered._events('trials'))==count
    events=recovered._events('holdouts')
    assert sum(e['action']=='falsification_result' for e in events)==1
    assert sum(e['action']=='opened' for e in events)==1


@pytest.mark.parametrize('after_replace',[False,True])
def test_holdout_finish_atomic_append_survives_publish_failure(tmp_path,registration,monkeypatch,after_replace):
    b,clock,result=pending_holdout(tmp_path,registration)
    original=(b.out/'holdouts.jsonl').read_bytes(); replace=mod.os.replace
    def fail(source,destination):
        if Path(destination)==b.out/'holdouts.jsonl':
            if after_replace: replace(source,destination)
            raise OSError('simulated publication failure')
        return replace(source,destination)
    with monkeypatch.context() as scoped:
        scoped.setattr(mod.os,'replace',fail)
        with pytest.raises(OSError): b.finish_trial('h',result)
    assert (b.out/'holdouts.jsonl').read_bytes().startswith(original)
    b.verify_heads(b.export_heads())
    assert mod.ResearchLedger(b.out,clock=clock).finish_trial('h',result)['passed']
    assert sum(e['action']=='falsification_result' for e in b._events('holdouts'))==1
