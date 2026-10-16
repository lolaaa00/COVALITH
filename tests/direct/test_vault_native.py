"""Native storage-layout and empty-state safety checks for the vault."""
from pathlib import Path
import json
import pytest

pytest.importorskip('gltest')


def _sdk_address(raw):
    from gltest.direct.sdk_loader import setup_sdk_paths
    setup_sdk_paths(Path('contracts/protection_vault.py').resolve())
    from genlayer import Address
    return Address(raw)


def test_vault_native_storage_and_solvency(direct_deploy, direct_alice, direct_bob):
    vault = direct_deploy('contracts/protection_vault.py',
        _sdk_address(direct_alice), _sdk_address(direct_bob))
    assert json.loads(vault.get_counts()) == {'policies': 0, 'pools': 0, 'transfer_attempts': 0}
    solvency = json.loads(vault.get_solvency())
    assert solvency['solvent'] is True
    assert solvency['pool_capital_wei'] == '0'
    assert solvency['withdrawal_credits_wei'] == '0'


def test_vault_native_rejects_unknown_pool_and_empty_credit(direct_deploy, direct_alice, direct_bob):
    vault = direct_deploy('contracts/protection_vault.py',
        _sdk_address(direct_alice), _sdk_address(direct_bob))
    with pytest.raises(Exception, match='pool not found'):
        vault.get_pool(1)
    with pytest.raises(Exception, match='nothing to withdraw'):
        vault.withdraw_credit()
