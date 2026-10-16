"""Native GenVM nondeterminism and validator re-fetch tests."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

pytest.importorskip('gltest')


def _sdk_address(raw):
    from gltest.direct.sdk_loader import setup_sdk_paths
    setup_sdk_paths(Path('contracts/risk_engine.py').resolve())
    from genlayer import Address
    return Address(raw)


def _asset():
    return {
        'coingecko_id': 'usd-coin', 'coinpaprika_id': 'usdc-usd-coin',
        'lower_bps': 9800, 'upper_bps': 10200,
        'issuer_url': 'https://issuer.example/report',
        'independent_url': 'https://independent.example/report',
        'terms': 'Only current independently corroborated material events qualify.',
    }


def _market_mocks(vm, first=1.0, second=1.0):
    now = int(datetime.now(timezone.utc).timestamp())
    vm.mock_web(r'api\.coingecko\.com', {
        'status': 200,
        'body': json.dumps({'usd-coin': {'usd': first, 'last_updated_at': now}}),
    })
    vm.mock_web(r'api\.coinpaprika\.com', {
        'status': 200,
        'body': json.dumps({'quotes': {'USD': {'price': second}},
                            'last_updated': datetime.fromtimestamp(now, timezone.utc).isoformat()}),
    })


def test_native_validator_rejects_forged_depeg(direct_deploy, direct_vm, direct_alice, monkeypatch):
    engine = direct_deploy('contracts/risk_engine.py', _sdk_address(direct_alice))
    instance = object.__getattribute__(engine, '_instance')
    monkeypatch.setattr(type(instance), '_asset', lambda self, asset_id: _asset())
    _market_mocks(direct_vm)
    engine.assess_depeg(1)
    forged = {'status': 'TRIGGERED', 'direction': 'BELOW', 'a': 9700, 'b': 9700,
              'source_root': 'forged'}
    assert direct_vm.run_validator(leader_result=forged) is False


def test_native_validator_rejects_source_disagreement(direct_deploy, direct_vm, direct_alice, monkeypatch):
    engine = direct_deploy('contracts/risk_engine.py', _sdk_address(direct_alice))
    instance = object.__getattribute__(engine, '_instance')
    monkeypatch.setattr(type(instance), '_asset', lambda self, asset_id: _asset())
    _market_mocks(direct_vm, .97, .97)
    engine.assess_depeg(1)
    direct_vm.clear_mocks()
    _market_mocks(direct_vm, 1.0, 1.0)
    leader = {'status': 'TRIGGERED', 'direction': 'BELOW', 'a': 9700, 'b': 9700,
              'source_root': 'leader-observation'}
    assert direct_vm.run_validator(leader_result=leader) is False
