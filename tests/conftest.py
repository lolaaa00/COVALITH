"""Local GenLayer contract unit harness. This is not a GenVM or chain emulator.

Tests execute the real contract Python methods with deterministic substitutes for
storage, transaction context, cross-contract views and nondeterministic IO.
"""
import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
A = '0x' + 'a' * 40
B = '0x' + 'b' * 40
C = '0x' + 'c' * 40
R = '0x' + '1' * 40
E = '0x' + '2' * 40
V = '0x' + '3' * 40


class TreeMap(dict):
    @classmethod
    def __class_getitem__(cls, item):
        return cls


class API:
    def __init__(self):
        self.instance = None
    def view(self):
        return self.instance


class Return:
    def __init__(self, calldata):
        self.calldata = calldata


class UserError(Exception):
    pass


class EVM:
    def __init__(self):
        self.outbox = []
    def contract_interface(self, cls):
        engine = self
        class Typed:
            def __init__(self, addr):
                self.addr = addr
            def emit_transfer(self, *, value):
                engine.outbox.append((self.addr, value))
        return Typed


@pytest.fixture
def env():
    gl = types.SimpleNamespace()
    gl.Contract = object
    gl.public = types.SimpleNamespace(write=types.SimpleNamespace(payable=lambda f:f),view=lambda f:f)
    # gl.public.write must itself be callable when no @payable.
    class Write:
        def __call__(self, f): return f
        def payable(self, f): return f
    gl.public.write = Write()
    gl.message = types.SimpleNamespace(sender_address=A,value=0,chain_id=61999)
    gl.vm = types.SimpleNamespace(UserError=UserError, Return=Return)
    gl.evm = EVM()
    gl.mock_contracts={}
    gl.get_contract_at = lambda addr: gl.mock_contracts[str(addr)]
    market = {'now':1_800_000_000,'a':1.0,'b':1.0,'issuer':'Redemptions are operating normally. No reserves shortfall.',
              'independent':'Issuer redemptions remain available with all reserves maintained.',
              'event':'NONE','poison':False,'stale':False}

    def feed(url):
        fresh=market['now'] - (14400 if market['stale'] else 0)
        if 'coingecko.com' in url:
            return types.SimpleNamespace(body=json.dumps({'usd-coin':{'usd':market['a'],'last_updated_at':fresh}}))
        if 'coinpaprika.com' in url:
            stamp=datetime.fromtimestamp(fresh,timezone.utc).isoformat()
            return types.SimpleNamespace(body=json.dumps({'quotes':{'USD':{'price':market['b']}},'last_updated':stamp}))
        raise Exception('unavailable market feed')

    def render(url, mode):
        return market['issuer'] if 'issuer' in url else market['independent']

    def execute(prompt, response_format='json'):
        if market['event']=='NONE':
            return {'event':'NONE','issuer_excerpt':'','independent_excerpt':''}
        if market['event']=='UNKNOWN':
            return {'event':'UNKNOWN','issuer_excerpt':'','independent_excerpt':''}
        a=market['issuer']; b=market['independent']
        return {'event':market['event'],'issuer_excerpt':a[:120],
                'independent_excerpt':b[:120] if not market['poison'] else 'fabricated quote'}

    gl.nondet=types.SimpleNamespace(web=types.SimpleNamespace(get=feed,render=render),exec_prompt=execute)
    def consensus(leader,validator):
        proposed=leader()
        if not validator(Return(proposed)):
            raise UserError('independent validators disagree')
        return proposed
    gl.vm.run_nondet_unsafe=consensus
    module=types.ModuleType('genlayer')
    module.gl=gl;module.TreeMap=TreeMap;module.Address=str;module.u256=int
    old=sys.modules.get('genlayer')
    sys.modules['genlayer']=module
    contracts={}
    for name in ['asset_registry','risk_engine','protection_vault']:
        spec=importlib.util.spec_from_file_location('unit_'+name,ROOT/'contracts'/f'{name}.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        mod.timestamp=lambda:market['now']
        contracts[name]=mod
    registry=contracts['asset_registry'].AssetRegistry()
    registry.records=TreeMap()
    gl.mock_contracts[R]=API();gl.mock_contracts[R].instance=registry
    engine=contracts['risk_engine'].RiskEngine(R)
    engine.assessments=TreeMap();engine.latest=TreeMap()
    gl.mock_contracts[E]=API();gl.mock_contracts[E].instance=engine
    vault=contracts['protection_vault'].ProtectionVault(R,E)
    vault.pools=TreeMap();vault.policies=TreeMap();vault.credits=TreeMap();vault.transfer_attempts=TreeMap()
    gl.mock_contracts[V]=API();gl.mock_contracts[V].instance=vault

    def sender(address,value=0):
        gl.message.sender_address=address
        gl.message.value=value
        if value:
            vault.balance=getattr(vault,'balance',0)+value

    def asset():
        sender(A)
        return registry.register_asset('USDC','usd-coin','usdc-usd-coin',
            'https://issuer.example/disclosures','https://independent.example/report',
            'Redemption suspensions and independently corroborated material reserve impairment trigger coverage.',
            9800,10200,0)

    def clear(i):
        market.update(a=1.0,b=1.0,event='NONE',stale=False,poison=False)
        engine.assess_depeg(i)
        engine.assess_collateral(i)

    def pool(i,capital=100*10**18,max_cover=10*10**18,kind='DEPEG'):
        sender(A,capital)
        return vault.create_pool(i,kind,max_cover,500,7)

    def cover(pid,amount=2*10**18,days=3,buyer=B):
        p=json.loads(vault.get_pool(pid))
        premium=contracts['protection_vault'].quoted_premium(amount,p['premium_rate_bps'],days)
        sender(buyer,premium)
        return vault.buy_protection(pid,amount,days)

    yield types.SimpleNamespace(gl=gl, market=market,reg=registry,engine=engine,vault=vault,
             sender=sender,asset=asset,clear=clear,pool=pool,cover=cover,
             modules=contracts,errors=UserError)
    if old is None:sys.modules.pop('genlayer',None)
    else:sys.modules['genlayer']=old
