#!/usr/bin/env python3
"""Read-only Studionet deployment source parity and finalized receipt verifier.

Usage: python tools/verify_deployment.py deploy/deployments.json
Requires user-supplied real addresses and tx hashes. Never guesses them.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
RPC='https://studio.genlayer.com/api'
CONTRACT_NAMES={'registry':'asset_registry.py','engine':'risk_engine.py','vault':'protection_vault.py'}


def rpc(method,*params):
    payload=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':list(params)}).encode()
    req=Request(RPC,data=payload,headers={'Content-Type':'application/json','User-Agent':'COVALITH-deployment-verifier/1.0'},method='POST')
    with urlopen(req,timeout=22) as res:
        result=json.loads(res.read(2_000_000))
    if 'error' in result or 'result' not in result:raise RuntimeError(f'{method}: {result.get("error", "missing result")}')
    return result['result']


def verify(config):
    verified={}
    for role,file in CONTRACT_NAMES.items():
        info=config[role]
        addr=info.get('address','');tx=info.get('deploy_tx','')
        if not re.fullmatch(r'0x[0-9a-fA-F]{40}',addr) or not re.fullmatch(r'0x[0-9a-fA-F]{64}',tx):
            raise ValueError(f'{role}: actual deployment address and transaction hash required')
        receipt=rpc('eth_getTransactionByHash',tx)
        receipt_id=receipt.get('hash') or receipt.get('tx_id')
        status=receipt.get('status_name') or receipt.get('statusName') or receipt.get('status')
        if not receipt_id or receipt_id.lower()!=tx.lower() or str(status).lower()!='finalized':
            raise RuntimeError(f'{role}: deployment receipt not finalized or wrong identity')
        contract_address=(receipt.get('data') or {}).get('contract_address') or receipt.get('recipient')
        leaders=(receipt.get('consensus_data') or {}).get('leader_receipt') or []
        if isinstance(leaders,dict):leaders=[leaders]
        successful=(receipt.get('result_name')=='MAJORITY_AGREE' or receipt.get('result')==6)
        successful=successful and bool(leaders) and all(r.get('execution_result')=='SUCCESS' for r in leaders)
        if not successful or not contract_address or contract_address.lower()!=addr.lower():
            raise RuntimeError(f'{role}: deployment execution did not finish successfully')
        code=base64.b64decode(rpc('gen_getContractCode',addr),validate=True)
        source=(ROOT/'contracts'/file).read_bytes()
        if code!=source:raise RuntimeError(f'{role}: finalized source bytes differ from local contract')
        schema=rpc('gen_getContractSchema',addr)
        if not isinstance(schema,dict) or not schema.get('methods'):
            raise RuntimeError(f'{role}: invalid finalized contract ABI')
        verified[role]={'address':addr,'deploy_tx':tx,'source_sha256':hashlib.sha256(source).hexdigest(),
                        'method_count':len(schema['methods']),'receipt_status':status,
                        'source_parity':True}
    print(json.dumps({'network':'studionet','chain_id':61999,'rpc':RPC,'verified':verified},indent=2))

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python tools/verify_deployment.py deploy/deployments.json')
    verify(json.loads(Path(sys.argv[1]).read_text()))
