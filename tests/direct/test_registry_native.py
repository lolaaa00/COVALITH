"""Official GenLayer Direct Mode contract execution. Requires genlayer-test + SDK.

This test executes the registry with the installed SDK, NOT the isolated unit shim.
"""
import json
import pytest
pytest.importorskip('gltest')


def test_registered_asset_native(direct_deploy, direct_vm, direct_alice, direct_bob):
    registry = direct_deploy('contracts/asset_registry.py')
    direct_vm.sender = direct_alice
    asset_id = registry.register_asset('USDC', 'usd-coin', 'usdc-usd-coin',
        'https://issuer.example/attestations', 'https://independent.example/reports',
        'Public redemption freezes and independently corroborated reserve impairments count as material events.',
        9800, 10200, 0)
    item = json.loads(registry.get_asset(asset_id))
    assert item['symbol'] == 'USDC'
    assert item['lower_bps'] == 9800
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert('successor must be authored'):
        registry.register_asset('USDC', 'usd-coin', 'usdc-usd-coin',
            'https://issuer.example/attestations', 'https://independent.example/reports',
            'Public redemption freezes and independently corroborated reserve impairments count as material events.',
            9800, 10200, asset_id)


def test_registry_native_rejects_unsafe_source_and_same_publisher(direct_deploy):
    registry = direct_deploy('contracts/asset_registry.py')
    terms = 'A current redemption freeze or independently verified reserve impairment is a material event.'
    with pytest.raises(Exception, match='bounded HTTPS'):
        registry.register_asset('USDC', 'usd-coin', 'usdc-usd-coin',
            'http://issuer.example/report', 'https://independent.example/report',
            terms, 9800, 10200, 0)
    with pytest.raises(Exception, match='independent domains'):
        registry.register_asset('USDC', 'usd-coin', 'usdc-usd-coin',
            'https://issuer.example/report', 'https://issuer.example/other',
            terms, 9800, 10200, 0)


def test_registry_native_successor_is_new_immutable_record(direct_deploy, direct_vm, direct_alice):
    registry = direct_deploy('contracts/asset_registry.py')
    direct_vm.sender = direct_alice
    terms = 'A current redemption freeze or independently verified reserve impairment is a material event.'
    first = registry.register_asset('USDC', 'usd-coin', 'usdc-usd-coin',
        'https://issuer.example/v1', 'https://independent.example/v1', terms, 9800, 10200, 0)
    second = registry.register_asset('USDC', 'usd-coin', 'usdc-usd-coin',
        'https://issuer.example/v2', 'https://independent.example/v2', terms, 9700, 10300, first)
    assert first == 1 and second == 2
    assert json.loads(registry.get_asset(first))['issuer_url'].endswith('/v1')
    assert json.loads(registry.get_asset(second))['predecessor'] == 1
    assert len(json.loads(registry.list_assets(1, 30))) == 2


@pytest.mark.parametrize('lower,upper', [(8499, 10200), (9901, 10200), (9800, 10099), (9800, 11501)])
def test_registry_native_rejects_trigger_bounds(direct_deploy, lower, upper):
    registry = direct_deploy('contracts/asset_registry.py')
    with pytest.raises(Exception, match='trigger outside|threshold outside'):
        registry.register_asset('USDC', 'usd-coin', 'usdc-usd-coin',
            'https://issuer.example/report', 'https://independent.example/report',
            'A current redemption freeze or independently verified reserve impairment is a material event.',
            lower, upper, 0)
