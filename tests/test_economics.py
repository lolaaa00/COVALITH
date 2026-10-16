import json
import random
import pytest
from conftest import A,B,C
WEI=10**18


def prepared(env):
    a=env.asset();env.clear(a);pid=env.pool(a)
    return a,pid

def test_end_to_end_depeg_claim(env):
    a,pid=prepared(env);policy=env.cover(pid)
    p=json.loads(env.vault.get_policy(policy));assert p['state']=='ACTIVE'
    assert int(json.loads(env.vault.get_pool(pid))['reserved'])==2*WEI
    env.market['now']+=3601
    env.market.update(a=.971,b=.970)
    finding=env.engine.assess_depeg(a)
    env.sender(B)
    env.vault.claim_protection(policy,finding)
    assert env.vault.get_credit(B)==2*WEI
    assert json.loads(env.vault.get_policy(policy))['state']=='PAID_TO_CREDIT'
    with pytest.raises(env.errors):env.vault.claim_protection(policy,finding)
    assert json.loads(env.vault.get_solvency())['solvent']

def test_mismatch_risk_category(env):
    a,pid=prepared(env);pol=env.cover(pid)
    env.market['now']+=3700
    env.market.update(event='REDEMPTION_BLOCKED',issuer='Issuer confirms all redemptions are now halted pending audit.',
                      independent='Independent source confirms all redemption activity stopped by issuer.')
    finding=env.engine.assess_collateral(a);env.sender(B)
    with pytest.raises(env.errors):env.vault.claim_protection(pol,finding)

def test_no_claim_during_inception_delay(env):
    a,pid=prepared(env);pol=env.cover(pid)
    env.market.update(a=.971,b=.971)
    finding=env.engine.assess_depeg(a);env.sender(B)
    with pytest.raises(env.errors,match='outside coverage'):env.vault.claim_protection(pol,finding)

def test_underwriter_cannot_drain_reserved(env):
    a,pid=prepared(env);env.cover(pid)
    pool=json.loads(env.vault.get_pool(pid));env.sender(A)
    with pytest.raises(env.errors):env.vault.redeem_free_capital(pid,int(pool['capital']))
    assert env.vault.get_credit(A)==0

def test_bad_or_stale_risk_blocks_buy(env):
    a,pid=prepared(env)
    env.market['now']+=21601
    with pytest.raises(env.errors,match='stale'):
        env.cover(pid)
    env.clear(a)
    env.market.update(a=.93,b=.93)
    env.engine.assess_depeg(a)
    with pytest.raises(env.errors,match='not been cleared'):
        env.cover(pid)

def test_exact_premium_and_capacity(env):
    a,pid=prepared(env)
    price=env.vault.quote_premium(pid,2*WEI,3)
    env.sender(B,price+1)
    with pytest.raises(env.errors,match='premium'):
        env.vault.buy_protection(pid,2*WEI,3)
    env.cover(pid,amount=10*WEI)
    env.sender(A)
    free=int(json.loads(env.vault.get_pool(pid))['capital'])-10*WEI
    env.vault.redeem_free_capital(pid,free)
    with pytest.raises(env.errors,match='free collateral'):
        env.cover(pid,amount=10*WEI)

def test_expiration_frees_reserved_amount(env):
    a,pid=prepared(env);pol=env.cover(pid,days=1)
    env.market['now']+=3600+86400+86401
    env.sender(C);env.vault.expire_policy(pol)
    assert int(json.loads(env.vault.get_pool(pid))['reserved'])==0
    assert json.loads(env.vault.get_policy(pol))['state']=='EXPIRED'
    with pytest.raises(env.errors):env.vault.expire_policy(pol)

def test_expired_policy_not_revived_by_late_assessment(env):
    a,pid=prepared(env);pol=env.cover(pid,days=1)
    env.market['now']+=3600+86400+10
    env.market.update(a=.90,b=.90)
    finding=env.engine.assess_depeg(a);env.sender(B)
    with pytest.raises(env.errors,match='outside coverage'):
        env.vault.claim_protection(pol,finding)

def test_wrong_holder_cannot_claim(env):
    a,pid=prepared(env);pol=env.cover(pid)
    env.market['now']+=3601;env.market.update(a=.96,b=.96)
    finding=env.engine.assess_depeg(a);env.sender(C)
    with pytest.raises(env.errors,match='only holder'):env.vault.claim_protection(pol,finding)

def test_withdrawal_consumes_credit_exactly_once(env):
    a,pid=prepared(env);env.sender(A)
    env.vault.redeem_free_capital(pid,WEI)
    assert env.vault.get_credit(A)==WEI
    env.vault.withdraw_credit()
    assert env.vault.get_credit(A)==0
    assert len(env.gl.evm.outbox)==1 and env.gl.evm.outbox[0]==(A,WEI)
    with pytest.raises(env.errors):env.vault.withdraw_credit()
    att=json.loads(env.vault.get_transfer_attempt(1))
    assert att['state']=='QUEUED_EXTERNAL_TRANSFER'

def test_only_underwriter_can_fund_or_pause(env):
    a,pid=prepared(env);env.sender(B)
    with pytest.raises(env.errors):env.vault.set_pool_paused(pid,True)
    with pytest.raises(env.errors):env.vault.fund_pool(pid)

def test_multiple_coverage_reserve_conservation(env):
    rng=random.Random(69199)
    for scenario in range(40):
        a,pid=prepared(env) if scenario==0 else (1,1)
        # Reset via independent fresh pools for each scenario.
        if scenario>0:
            env.clear(1);pid=env.pool(1,capital=100*WEI)
        policies=[]
        outstanding=0
        for index in range(rng.randint(2,10)):
            amt=rng.randint(1,5)*WEI
            pol=env.cover(pid,amount=amt,days=3,buyer=B if index%2 else C)
            policies.append(pol);outstanding+=amt
            pool=json.loads(env.vault.get_pool(pid))
            assert int(pool['reserved'])==outstanding
            assert int(pool['capital'])>=int(pool['reserved'])
        env.market['now']+=3601
        env.market.update(a=.97,b=.971)
        assessment=env.engine.assess_depeg(1)
        for pol in policies[:rng.randint(0,len(policies))]:
            rec=json.loads(env.vault.get_policy(pol));env.sender(rec['holder'])
            env.vault.claim_protection(pol,assessment)
            outstanding-=int(rec['cover_wei'])
            assert int(json.loads(env.vault.get_pool(pid))['reserved'])==outstanding
            assert json.loads(env.vault.get_solvency())['solvent']
        env.market['now']+=86400*4+86401
        for pol in policies:
            rec=json.loads(env.vault.get_policy(pol))
            if rec['state']=='ACTIVE':env.vault.expire_policy(pol)
        assert int(json.loads(env.vault.get_pool(pid))['reserved'])==0
