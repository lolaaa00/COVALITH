# COVALITH

**Independent collateral intelligence and capital-backed protection on GenLayer.**

COVALITH is a Studionet prototype for source-grounded depeg and collateral impairment determination, fully reserved fixed-amount GEN protection, policy issuance, dispute-free consensus-triggered claims, and explicit settlement accounting.

**Network:** Studionet `61999` / `0xF22F`  
**RPC:** `https://studio.genlayer.com/api`  
**Explorer:** `https://explorer-studio.genlayer.com`  
**CLI:** repository-local `genlayer@0.39.1`  
**Frontend:** Next.js 15, React 19, `genlayer-js@1.1.8` and injected EIP-1193 provider signing.

## Scope and trust model

The prototype does **not** custody stablecoins, implement swaps, liquidations, or hold external collateral. It covers a reference asset but uses native GEN as the only pool capital, premium and payout unit. Protection is *not* a guarantee against a real-world loss. Never use real-value funding on the basis of the isolated tests alone.

An asset profile records a reference ticker, immutable source identities (CoinGecko/Coinpaprika market identifiers and issuer/independent publisher URLs), thresholds and collateral policy. Asset profiles are permissionlessly authored; **a registered profile is not a trusted asset endorsement**. Pool managers explicitly choose a profile and bear its source-selection risk.

Two independent consensus tracks determine:

- **DEPEG:** price readings from separate CoinGecko and Coinpaprika APIs. Both must breach the same threshold and be within a bounded divergence. Stale/missing/conflicting data returns `UNKNOWN`. Public APIs can rate limit, become unavailable, or change schema; those outages block protection purchases and triggering, rather than pretending a price is current.
- **COLLATERAL:** issuer disclosure and independent publisher evidence rendered by GenVM. The model must return exact supporting excerpts for a serious `REDEMPTION_BLOCKED` or `RESERVES_IMPAIRED` event. Independent validators independently reread evidence, derive their own result and verify the material event fields. `UNKNOWN` never triggers a payout. Two different domains are necessary but **do not cryptographically prove organizational independence**; the source authority remains an explicit trust assumption.

Evidence obtained from pages is untrusted text. A consensus finding is valid only for its defined source policy and observation time; it does not prove that the issuer has no other undisclosed issues. Validator disagreements and unavailable evidence may cause an inconclusive result.

## Contracts

| Contract | Purpose |
| --- | --- |
| `contracts/asset_registry.py` | Immutable asset profiles, policy bounds and versioned successors |
| `contracts/risk_engine.py` | Real GenVM web fetching, independent AI/price interpretation and consensus assessment records |
| `contracts/protection_vault.py` | GEN underwriting, exact premiums, locked policy reserve, time-gated claims, withdrawable credits and solvency views |

A `CLEAR` consensus result for **both** risk tracks no older than 6 hours is necessary to purchase new coverage. Coverage activates 1 hour after purchase. The vault locks the entire payout amount until it has been paid to holder credit or expired after the claim grace window. A matching `TRIGGERED` result assessed inside the policy interval is required before payout. The claim window lasts for 24 hours after policy expiry. This deliberately does not pay for an event detected before the insured interval or after it ends.

**Amounts:** Contract monetary record fields are represented as decimal strings, not JavaScript floating-point numbers. Use bigint/`u256` for every GEN value, including transaction `value`; transaction **fees are separate from premium/deposit GEN**.

**External withdrawals:** The credit is zeroed before the contract emits a finalized EVM-layer EOA transfer. The recorded state `QUEUED_EXTERNAL_TRANSFER` does **not** prove payment delivery; inspect the child transaction and recipient balance. GenLayer documentation warns that value held in a failed child message is not automatically refunded. This must be tested live before exposure is accepted.

## Repository

```text
contracts/              GenVM intelligent contracts
frontend/               Six-section Next.js DeFi workspace
  app/                   Landing and metadata
  components/            Interactive capital/risk/policy screens
  lib/chain.ts           Injected EIP-1193 signing and finalized reads
tests/                  Local contract-method, mutation and release checks
  direct/                Official SDK Direct Mode smoke verification
tools/preflight.py       Strict local dependency/lint/test gates
tools/verify_deployment.py  Live RPC finalized receipts and exact source parity
deploy/studionet.sh      Interactive protected multi-contract deployment
.github/workflows/       Clean CI checks
```

## Install and verify

Requirements: Node 22, Python 3.12+, functional internet, valid Studionet RPC, funded authorized deployment account, and the official GenVM SDK distribution.

```bash
npm install --no-audit --no-fund                  # root CLI must resolve to 0.39.1
npm --prefix frontend install --no-audit --no-fund
python -m pip install -r requirements-dev.txt

# Check native SDK against the pinned Depends header in all three contracts
genvm-lint setup --contract contracts/asset_registry.py
for c in contracts/*.py; do
  genvm-lint check "$c"
  genvm-lint typecheck "$c" --strict
done

python -m pytest -q tests                        # isolated tests + native Direct Mode
npm --prefix frontend run typecheck
npm --prefix frontend run build
python tools/preflight.py                        # fail-closed, no silent skipped SDK
```

The local Python tests execute the real Python contract methods using mocked GenLayer storage/message/consensus/web APIs. They are **not** official Direct Mode or a deployed consensus simulation. The separate `tests/direct` suite requires the real `genlayer-test` installation. Do not infer live payout or consensus correctness solely from either suite.

## Deploy to Studionet

Do **not** deploy unless `tools/preflight.py` passes, including actual GenVM semantic validation, a real Direct Mode run, and Next.js compilation. Validate the current selected network and CLI version before sending any transaction.

```bash
./node_modules/.bin/genlayer network set studionet
./node_modules/.bin/genlayer network info
bash deploy/studionet.sh
```

Deployment order: asset registry, finalized risk engine with registry address, finalized protection vault with registry and engine addresses. Wait for **successful finalized execution** of every deployment, not mere transaction acceptance. Copy `deploy/deployments.example.json` to `deploy/deployments.json`, enter genuine deployment hashes and addresses, then run:

```bash
python tools/verify_deployment.py deploy/deployments.json
```

The verifier requests source code with `status=finalized`, decodes base64, checks exact bytes against local source, retrieves ABI and ensures deployment receipts have finalized successful execution. It refuses missing or mismatched data.

The deployment script writes `frontend/.env.local` with the three verified contract addresses only after interactive confirmations. It does not create signing keys, run a background wallet, or invent transaction hashes.

### Current Studionet deployment

| Role | Finalized address |
| --- | --- |
| Registry | `0x95509D94C2a51E186430b10D804e2Fc284d39cE7` |
| Risk engine | `0xa6859840f0916e80A07da0b8B03D70e2facf5002` |
| Protection vault | `0x872f9d5A5CBa4F734a3fb35B2847C9e5e4491543` |

## End-to-end operating flow

1. Connect an **injected EIP-1193** account on chain `61999` (no Snaps, WalletConnect, custodial wallet, wallet-specific SDK, or server signatures).
2. Register an asset and independently inspect the URLs and risk policy. Asset profile IDs are immutable.
3. Run both assessment kinds; verify finalized `CLEAR` observations, real source URLs and timestamps.
4. Fund a pool using GEN. Pool capital can back many fixed-payout policies only if every reserved cover fits into the available unreserved balance.
5. Buy a policy with the **exact** GEN premium. The pool reserves its fixed cover amount. The policy has a 1-hour inception delay.
6. A later independently verified `TRIGGERED` risk result during the policy interval authorizes its holder to claim, moving locked pool capital to personal withdrawal credit.
7. After policy expiry and a full 24-hour claim grace window, anyone can expire an unclaimed policy and release its reservation.
8. A holder/underwriter can request a signed credit withdrawal. Verify external message finalization and actual recipient balance; never infer delivery from a queued record.

The UI distinguishes signed submission, accepted decision, finalized success and failure. Tracking errors preserve the submitted transaction hash and **never automatically resubmit a potentially duplicate write**. Reads target latest finalized state.

## Current validation status

The pinned local preflight and clean GitHub Actions run pass Python syntax, 51 isolated behavioral tests, 11 official Direct Mode tests, GenVM lint/validate/check/typecheck/schema for all contracts, TypeScript checks and the production frontend build. All three Studionet deployments reached `FINALIZED` with successful consensus, and the verifier confirmed exact deployed-source parity plus valid schemas. The external EOA withdrawal child-message delivery path and injected-wallet browser flow still require live manual testing; queued transfer state alone is not treated as proof of payment.

The first release should be treated as experimental Testnet infrastructure, not production financial protection. Independent security review, active publisher verification, economic stress tests, child-transfer recovery analysis, front-end browser testing and successful live GEN execution are essential before the product is entrusted with significant capital.

## Documentation

- [GenLayer Studionet](https://docs.genlayer.com/developers/intelligent-contracts/tools/genlayer-studio)
- [Value Transfers](https://docs.genlayer.com/developers/intelligent-contracts/features/value-transfers)
- [Inter-contract Views](https://docs.genlayer.com/developers/intelligent-contracts/features/interacting-with-intelligent-contracts)
- [Independent Validator Comparison](https://docs.genlayer.com/developers/intelligent-contracts/equivalence-principle)
- [Web Data Access](https://docs.genlayer.com/developers/intelligent-contracts/features/web-access)
- [GenVM Linter](https://docs.genlayer.com/api-references/genlayer-linter)
- [Official Direct Mode](https://docs.genlayer.com/api-references/genlayer-test/direct)
- [Browser Wallet SDK](https://docs.genlayer.com/developers/decentralized-applications/writing-data)
