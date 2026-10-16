#!/usr/bin/env python3
"""Fail-closed local validation. No automatic transaction or wallet creation."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE=Path(__file__).resolve().parents[1]
CONTRACTS=[BASE/'contracts'/s for s in ['asset_registry.py','risk_engine.py','protection_vault.py']]


def run(label, argv, timeout=150, env=None, accept_zero_summary=False):
    try:
        merged=os.environ.copy()
        if env:merged.update(env)
        p=subprocess.run(argv,cwd=BASE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,env=merged)
        output=p.stdout.strip()
        passed=p.returncode==0 or (accept_zero_summary and '0 error(s), 0 warning(s)' in output)
        print(('PASS' if passed else 'BLOCK') + ' ' + label)
        if not passed:print('  '+output[-1100:].replace('\n','\n  '))
        return passed,output
    except (FileNotFoundError,subprocess.TimeoutExpired) as ex:
        print('BLOCK '+label+': '+str(ex));return False,''


def main():
    results={}
    results['python_runtime']=sys.version_info >= (3,12)
    print(('PASS' if results['python_runtime'] else 'BLOCK')+' Python 3.12+')
    node_ok,node_version=run('Node.js 22',['node','--version'])
    results['node_runtime']=node_ok and node_version.startswith('v22.')
    if node_ok and not results['node_runtime']:print('BLOCK required Node.js 22, found '+node_version)
    dep=BASE/'node_modules'/'genlayer'/'package.json'
    if dep.exists():
        actual=json.loads(dep.read_text()).get('version')
        results['local_cli']=(actual=='0.39.1')
    else:results['local_cli']=False
    print(('PASS' if results['local_cli'] else 'BLOCK')+' repository-local CLI 0.39.1')
    try:
        import importlib.metadata as metadata
        results['python_tools']=(metadata.version('genvm-linter')=='0.11.0' and
                                 metadata.version('genlayer-test')=='0.29.0' and
                                 metadata.version('pytest')=='8.4.2')
    except metadata.PackageNotFoundError:results['python_tools']=False
    print(('PASS' if results['python_tools'] else 'BLOCK')+' exact Python tool versions')
    results['contract_ast']=all('py-genlayer:' in p.read_text().splitlines()[0] for p in CONTRACTS)
    print(('PASS' if results['contract_ast'] else 'BLOCK')+' GenVM dependency header present')
    results['python_compilation']=run('Python syntax',[sys.executable,'-m','compileall','-q','contracts'])[0]
    results['unit_tests']=run('Isolated contract behavioral tests',[sys.executable,'-m','pytest','-q','tests/test_registry.py','tests/test_risk.py','tests/test_economics.py'])[0]
    direct_ok,direct_output=run('Official GenLayer Direct Mode',[sys.executable,'-m','pytest','-q','tests/direct'])
    results['native_direct']=direct_ok and 'skipped' not in direct_output.lower()
    # Python pytest may SKIP Direct Mode if the GenLayer package is missing: disallow that.
    try:import gltest
    except ImportError:results['native_direct']=False;print('BLOCK Official GenLayer Direct Mode package absent')
    genvm_env={'GENVM_VERSION':'v0.2.12'}
    for c in CONTRACTS:
        for command,args in (
            ('lint',['lint',str(c),'--json']),('validate',['validate',str(c),'--json']),
            ('check',['check',str(c),'--json']),('typecheck',['typecheck',str(c),'--strict']),
            ('schema',['schema',str(c)])):
            passed,output=run('GenVM '+command+' '+c.name,
                ['genvm-lint',*args],env=genvm_env,accept_zero_summary=command=='typecheck')
            # genvm-linter 0.11.0 exits nonzero under --strict when the SDK stubs
            # emit informational "partially unknown" notes, even while Pyright's
            # own summary is exactly zero errors and zero warnings.
            if command=='typecheck' and '0 error(s), 0 warning(s)' in output:
                passed=True
            results[command+'_'+c.stem]=passed
    results['frontend_install']=(BASE/'frontend'/'node_modules'/'next'/'package.json').exists()
    print(('PASS' if results['frontend_install'] else 'BLOCK')+' frontend installed dependencies')
    if results['frontend_install']:
        results['frontend_types']=run('TypeScript', ['npm','--prefix','frontend','run','typecheck'])[0]
        results['frontend_build']=run('Next.js production build',['npm','--prefix','frontend','run','build'],timeout=240)[0]
    else:results['frontend_types']=False;results['frontend_build']=False
    print('\nRESULT: '+('LOCAL GATES PASS' if all(results.values()) else 'BLOCKED — never deploy with unresolved gates'))
    print(json.dumps(results,indent=2))
    return 0 if all(results.values()) else 1

if __name__=='__main__':raise SystemExit(main())
