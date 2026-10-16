import { createClient } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { ExecutionResult, TransactionHashVariant, TransactionStatus, type TransactionHash } from 'genlayer-js/types';

export const CHAIN_ID = 61999;
export const CHAIN_HEX = '0xf22f';
export const RPC = 'https://studio.genlayer.com/api';
export const EXPLORER = 'https://explorer-studio.genlayer.com';
export const isAddress = (s:string) => /^0x[0-9a-fA-F]{40}$/.test(s);
export const ADDRESSES = {
  registry: process.env.NEXT_PUBLIC_REGISTRY_ADDRESS || '',
  engine: process.env.NEXT_PUBLIC_ENGINE_ADDRESS || '',
  vault: process.env.NEXT_PUBLIC_VAULT_ADDRESS || '',
};
export const deployed = Object.values(ADDRESSES).every(isAddress);

export interface Provider {
  request(args: { method: string; params?: unknown[] | object }): Promise<unknown>;
  on?(event: string, handler: (...args: any[]) => void): void;
  removeListener?(event: string, handler: (...args: any[]) => void): void;
}
declare global { interface Window { ethereum?: Provider } }
export type TxPhase = 'ESTIMATING'|'SIGNING'|'SUBMITTED'|'DECIDED'|'FINALIZED'|'FAILED'|'INTERRUPTED';
export type Tx = {hash:string; method:string; phase:TxPhase; error?:string; created:number};
export const shorten = (s:string) => s.length>18?`${s.slice(0,9)}…${s.slice(-6)}`:s;
export function wei(s:string):bigint {
  if(!/^\d+(\.\d{1,18})?$/.test(s)) throw Error('Enter a valid GEN value (maximum 18 decimal places)');
  const [whole, fraction=''] = s.split('.');
  return BigInt(whole)*10n**18n + BigInt(fraction.padEnd(18,'0'));
}
export function gen(v:string|number|bigint):string {
  const n=BigInt(v); const dec=(n%10n**18n).toString().padStart(18,'0').slice(0,4);
  return `${n/10n**18n}.${dec} GEN`;
}
export function count(value:unknown):number {return Number(value || 0)}
export function client() {return createClient({chain:studionet})}
export async function read<T=unknown>(address:string, functionName:string, args:unknown[]=[]):Promise<T> {
  if(!isAddress(address)) throw Error('Contracts not configured. Set NEXT_PUBLIC_* addresses after deployment.');
  return await client().readContract({ address:address as `0x${string}`, functionName,
    args:args as any[], transactionHashVariant:TransactionHashVariant.LATEST_FINAL }) as T;
}
export async function switchChain(provider:Provider) {
  try {await provider.request({method:'wallet_switchEthereumChain',params:[{chainId:CHAIN_HEX}]});}
  catch(e:any) {
    if(e?.code !== 4902) throw e;
    await provider.request({method:'wallet_addEthereumChain',params:[{
      chainId:CHAIN_HEX,chainName:'GenLayer Studionet',nativeCurrency:{name:'GEN',symbol:'GEN',decimals:18},
      rpcUrls:[RPC],blockExplorerUrls:[EXPLORER],
    }]});
  }
  const id = String(await provider.request({method:'eth_chainId'}));
  if(Number.parseInt(id,16)!==CHAIN_ID) throw Error('Wallet is not on Studionet 61999');
}
export async function connect() {
  const provider=window.ethereum;
  if(!provider) throw Error('Install or enable an injected EIP-1193 wallet; Snaps and WalletConnect are not supported.');
  const accounts=await provider.request({method:'eth_requestAccounts'}) as string[];
  if(!accounts?.[0] || !isAddress(accounts[0])) throw Error('No injected account selected');
  const id=String(await provider.request({method:'eth_chainId'}));
  return {account:accounts[0],chain:Number.parseInt(id,16)};
}
export async function submit(account:string, address:string, method:string, args:unknown[], value:bigint|undefined,
  report:(phase:TxPhase,hash?:string,error?:string)=>void):Promise<string> {
  const provider=window.ethereum;
  if(!provider) throw Error('No injected EIP-1193 wallet');
  if(!isAddress(address)) throw Error('Contract address is missing');
  const id=String(await provider.request({method:'eth_chainId'}));
  const accounts=await provider.request({method:'eth_accounts'}) as string[];
  if(Number.parseInt(id,16)!==CHAIN_ID || !accounts.some(a=>a.toLowerCase()===account.toLowerCase()))
    throw Error('Wrong network or wallet account changed; reconnect before signing');
  const wallet=createClient({chain:studionet,account:account as `0x${string}`,provider:provider as any});
  await wallet.connect('studionet');
  const call={address:address as `0x${string}`,functionName:method,args:args as any[],value:value ?? 0n};
  report('ESTIMATING');
  await wallet.simulateWriteContract(call);
  // Recheck account/chain immediately prior to signing.
  if(Number.parseInt(String(await provider.request({method:'eth_chainId'})),16)!==CHAIN_ID ||
    !(await provider.request({method:'eth_accounts'}) as string[]).some(a=>a.toLowerCase()===account.toLowerCase()))
    throw Error('Wallet changed during fee estimation; submission cancelled');
  report('SIGNING');
  const hash=await wallet.writeContract(call) as TransactionHash;
  report('SUBMITTED',hash);
  try {
    const decision=await wallet.waitForTransactionReceipt({hash,status:TransactionStatus.ACCEPTED});
    if(decision.txExecutionResultName===ExecutionResult.FINISHED_WITH_ERROR){report('FAILED',hash,`Decision: ${decision.statusName} / ${decision.txExecutionResultName}`);return hash;}
    report('DECIDED',hash);
    const final=await wallet.waitForTransactionReceipt({hash,status:TransactionStatus.FINALIZED});
    const successful=final.statusName===TransactionStatus.FINALIZED &&
      final.txExecutionResultName===ExecutionResult.FINISHED_WITH_RETURN;
    report(successful?'FINALIZED':'FAILED',hash,
      successful?undefined:`Finalization: ${final.statusName} / ${final.txExecutionResultName}`);
  }catch(e:any) {
    report('INTERRUPTED',hash,`Tracking interrupted (${e?.message || e}). Inspect this hash before retrying.`);
  }
  return hash;
}
export async function recover(hash:string):Promise<{phase:TxPhase,error?:string}> {
  if(!/^0x[0-9a-fA-F]{64}$/.test(hash))throw Error('Malformed transaction hash');
  const final=await client().waitForTransactionReceipt({hash:hash as TransactionHash,status:TransactionStatus.FINALIZED});
  return final.statusName===TransactionStatus.FINALIZED &&
    final.txExecutionResultName===ExecutionResult.FINISHED_WITH_RETURN
    ?{phase:'FINALIZED'}:{phase:'FAILED',error:`${final.statusName} / ${final.txExecutionResultName}`};
}
