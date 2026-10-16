#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Strict network version and local deployment gate. Requires a funded authorized CLI account.
python tools/preflight.py
CLI="./node_modules/.bin/genlayer"
[[ -x "$CLI" ]] || { echo 'Local CLI 0.39.1 not installed'; exit 1; }
"$CLI" network set studionet
"$CLI" network info
printf '\nNetwork MUST be 61999 / https://studio.genlayer.com/api. Confirm (type 61999): '
read -r CHAIN
[[ "$CHAIN" == '61999' ]] || exit 1

"$CLI" deploy --contract contracts/asset_registry.py --rpc https://studio.genlayer.com/api
printf '\nEnter the FINALIZED registry address (0x...): '
read -r REG
[[ "$REG" =~ ^0x[0-9a-fA-F]{40}$ ]] || { echo Invalid; exit 1; }
"$CLI" deploy --contract contracts/risk_engine.py --rpc https://studio.genlayer.com/api --args "$REG"
printf '\nEnter the FINALIZED engine address (0x...): '
read -r ENG
[[ "$ENG" =~ ^0x[0-9a-fA-F]{40}$ ]] || { echo Invalid; exit 1; }
"$CLI" deploy --contract contracts/protection_vault.py --rpc https://studio.genlayer.com/api --args "$REG" "$ENG"
printf '\nEnter the FINALIZED vault address (0x...): '
read -r VAULT
[[ "$VAULT" =~ ^0x[0-9a-fA-F]{40}$ ]] || { echo Invalid; exit 1; }
cat > frontend/.env.local <<EOF
NEXT_PUBLIC_REGISTRY_ADDRESS=$REG
NEXT_PUBLIC_ENGINE_ADDRESS=$ENG
NEXT_PUBLIC_VAULT_ADDRESS=$VAULT
EOF
printf '\nFor EVERY deployment, record its genuine finalized tx hash in deploy/deployments.json\n'
printf 'Then run python tools/verify_deployment.py deploy/deployments.json\n'
