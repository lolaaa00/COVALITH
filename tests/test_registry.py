import json
import pytest
from conftest import A, B


def test_register_and_read(env):
    i=env.asset(); assert i==1
    record=json.loads(env.reg.get_asset(i))
    assert record['symbol']=='USDC'
    assert record['lower_bps']==9800
    assert env.reg.get_asset_count()==1
    assert len(json.loads(env.reg.list_assets(1,30)))==1

@pytest.mark.parametrize('url',[
    'http://issuer.example/a','https://localhost/a','https://127.0.0.1/a','https://example.local/a',
    'https://example.com:8443/a','https://example.com@other.com/a','https://10.0.0.2/a',
    'https://issuer.example/a?admin=1', 'https://issuer.example/a#x'])
def test_invalid_sources(env,url):
    with pytest.raises(env.errors):
        env.reg.register_asset('USDC','usd-coin','usdc-usd-coin',url,'https://independent.example/a',
            'Source-defined collateral policy for the represented asset.',9800,10200,0)

@pytest.mark.parametrize('lower,upper',[(900,10200),(9901,10200),(9800,10090),(9800,11600)])
def test_risk_limits(env,lower,upper):
    with pytest.raises(env.errors):
        env.reg.register_asset('USDC','usd-coin','usdc-usd-coin','https://issuer.example/a',
            'https://independent.example/a','Source-defined collateral policy for the represented asset.',lower,upper,0)

def test_succession_requires_same_author(env):
    env.asset();env.sender(B)
    with pytest.raises(env.errors):
        env.reg.register_asset('USDC','usd-coin','usdc-usd-coin','https://issuer.example/a',
            'https://independent.example/a','Source-defined collateral policy for the represented asset.',9800,10200,1)

def test_independent_publisher_host(env):
    with pytest.raises(env.errors):
        env.reg.register_asset('USDC','usd-coin','usdc-usd-coin','https://issuer.example/a',
            'https://issuer.example/b','Source-defined collateral policy for the represented asset.',9800,10200,0)
