"""Offline source and product integration checks; not a replacement for RPC execution."""
from pathlib import Path
import ast
import re
import json

ROOT=Path(__file__).resolve().parents[1]
CONTRACTS={x.stem:x for x in (ROOT/'contracts').glob('*.py')}
FRONT=(ROOT/'frontend'/'components'/'Workspace.tsx').read_text()
WALLET=(ROOT/'frontend'/'lib'/'chain.ts').read_text()

def public_methods(path):
    mod=ast.parse(path.read_text())
    return {n.name for c in mod.body if isinstance(c,ast.ClassDef) for n in c.body
            if isinstance(n,ast.FunctionDef) and any(ast.unparse(d).startswith('gl.public.') for d in n.decorator_list)}


def test_each_contract_depends_on_pinned_sdk():
    for path in CONTRACTS.values():assert path.read_text().startswith('# { "Depends": "py-genlayer:')


def test_client_targets_exact_chain():
    assert 'CHAIN_ID = 61999' in WALLET
    assert "CHAIN_HEX = '0xf22f'" in WALLET
    assert "https://studio.genlayer.com/api" in WALLET


def test_no_backend_private_key_signing():
    for term in ['privateKeyToAccount','createAccount()', 'eth_sendRawTransaction','@metamask',
                 '@walletconnect/','createWalletClient','genlayer-snap', 'walletClient.sendTransaction']:
        assert term not in WALLET,term
    assert "method:'eth_requestAccounts'" in WALLET
    assert "method:'eth_accounts'" in WALLET
    assert "method:'eth_chainId'" in WALLET
    assert "method:'wallet_switchEthereumChain'" in WALLET
    assert 'provider:provider as any' in WALLET


def test_financial_calls_have_real_contract_methods():
    registry=public_methods(CONTRACTS['asset_registry'])
    engine=public_methods(CONTRACTS['risk_engine'])
    vault=public_methods(CONTRACTS['protection_vault'])
    for method in ['register_asset','get_asset_count','list_assets']:
        assert method in registry
    for method in ['assess_depeg','assess_collateral','get_assessment','get_latest','list_assessments']:
        assert method in engine
    for method in ['create_pool','buy_protection','claim_protection','withdraw_credit',
                   'expire_policy','fund_pool','redeem_free_capital','list_policies','quote_premium',
                   'list_pools','get_credit','get_solvency','get_counts']:
        assert method in vault


def test_all_payable_methods_explicit():
    txt=CONTRACTS['protection_vault'].read_text()
    for method in ('create_pool','fund_pool','buy_protection'):
        assert re.search(r'@gl.public.write.payable\s+def '+method+r'\(',txt)
    for method in ('claim_protection','expire_policy','redeem_free_capital','withdraw_credit'):
        assert re.search(r'@gl.public.write\s+def '+method+r'\(',txt)


def test_transfer_finality_and_no_free_unreserved_custody():
    txt=CONTRACTS['protection_vault'].read_text()
    assert "emit_transfer(value=amount)" in txt
    assert "pool['capital'] - pool['reserved']" in txt
    assert 'CLAIM_GRACE' in txt
    assert "state': 'QUEUED_EXTERNAL_TRANSFER'" in txt


def test_protocol_uses_real_independent_validator_comparison():
    txt=CONTRACTS['risk_engine'].read_text()
    assert txt.count('gl.vm.run_nondet_unsafe')==2
    assert 'independently = observe()' in txt
    assert 'own = observe()' in txt
    assert "p.get('status') != own['status']" in txt
    assert "proposed.get('event') != independently['event']" in txt


def test_risk_unknown_never_authorizes_payout():
    txt=CONTRACTS['protection_vault'].read_text()
    assert "assessment['status'] == 'TRIGGERED'" in txt
    assert "result['status'] == 'CLEAR'" in txt
    assert 'INCEPTION_DELAY' in txt


def test_no_synthetic_demo_numbers():
    assert "createAccount()" not in WALLET
    assert 'No sample balances are displayed' in FRONT
    assert 'no fabricated escrow amounts' not in FRONT.lower() or 'No fabricated escrow amounts' in FRONT


def test_no_handover_files():
    assert not list(ROOT.rglob('*HANDOFF*.md'))
