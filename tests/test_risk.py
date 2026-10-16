import json
import pytest

@pytest.mark.parametrize('a,b,result',[
    (1,1,'CLEAR'),(.972,.974,'TRIGGERED'),(1.027,1.028,'TRIGGERED'),
    (.977,.985,'UNKNOWN'),(.95,.97,'UNKNOWN'),(.98,.98,'CLEAR'),(1.02,1.02,'CLEAR')])
def test_consensus_market_feed(env,a,b,result):
    asset=env.asset();env.market.update(a=a,b=b)
    i=env.engine.assess_depeg(asset)
    assert json.loads(env.engine.get_assessment(i))['status']==result

def test_stale_price_rejected(env):
    asset=env.asset();env.market.update(stale=True,a=.93,b=.93)
    idx=env.engine.assess_depeg(asset)
    assert json.loads(env.engine.get_assessment(idx))['status']=='UNKNOWN'

def test_collateral_clear(env):
    asset=env.asset();i=env.engine.assess_collateral(asset)
    assert json.loads(env.engine.get_assessment(i))['status']=='CLEAR'

def test_collateral_both_sources_required(env):
    asset=env.asset();env.market.update(
        issuer='Issuer confirms all redemptions have been suspended due to reserve restrictions.',
        independent='Independent publisher confirms redemptions suspended and reserves impaired.',
        event='REDEMPTION_BLOCKED')
    idx=env.engine.assess_collateral(asset)
    assert json.loads(env.engine.get_assessment(idx))['status']=='TRIGGERED'

def test_model_fabricated_quote_fails_closed(env):
    asset=env.asset();env.market.update(event='REDEMPTION_BLOCKED',poison=True)
    idx=env.engine.assess_collateral(asset)
    assert json.loads(env.engine.get_assessment(idx))['status']=='UNKNOWN'

def test_validator_detects_malicious_leader(env):
    a=env.asset()
    def attack(leader,validator):
        good=leader()
        forged=dict(good,status='TRIGGERED',direction='BELOW',a=9700,b=9690)
        if not validator(env.gl.vm.Return(forged)):
            raise env.errors('validators detected forged assessment')
        return forged
    env.gl.vm.run_nondet_unsafe=attack
    with pytest.raises(env.errors,match='forged assessment'):
        env.engine.assess_depeg(a)
    assert env.engine.get_assessment_count()==0

def test_latest_and_pagination(env):
    a=env.asset();env.engine.assess_depeg(a);env.engine.assess_collateral(a)
    assert json.loads(env.engine.get_latest(a,'DEPEG'))['kind']=='DEPEG'
    assert len(json.loads(env.engine.list_assessments(1,10)))==2
