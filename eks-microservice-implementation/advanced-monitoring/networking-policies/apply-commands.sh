#!/usr/bin/env bash
# Apply all NetworkPolicy manifests — REVIEW FIRST, run manually when ready.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Dry-run:"
kubectl apply -f "${SCRIPT_DIR}/" --dry-run=client

echo ""
echo "To apply for real:"
echo "  kubectl apply -f ${SCRIPT_DIR}/"
echo ""
echo "Verify:"
echo "  kubectl get networkpolicy -n ecommerce"
