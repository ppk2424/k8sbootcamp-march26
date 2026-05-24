#!/usr/bin/env bash
# Istio install commands for eks-cluster — REVIEW ONLY, not executed by default.
# Run each section manually when ready. See README.md for full guide.
set -euo pipefail

echo "=== Istio install (control plane) ==="
cat <<'EOF'
helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo update

kubectl create namespace istio-system --dry-run=client -o yaml | kubectl apply -f -

helm install istio-base istio/base \
  -n istio-system \
  --set defaultRevision=default \
  --wait

helm install istiod istio/istiod \
  -n istio-system \
  --wait \
  --set meshConfig.enablePrometheusMerge=true \
  --set meshConfig.defaultConfig.holdApplicationUntilProxyStarts=true

kubectl get pods -n istio-system
EOF

echo ""
echo "=== Enable sidecar injection + apply mesh policies ==="
cat <<'EOF'
kubectl label namespace ecommerce istio-injection=enabled --overwrite
kubectl apply -f advanced-monitoring/service-mesh/
kubectl rollout restart deployment,statefulset -n ecommerce
kubectl get pods -n ecommerce -w
EOF

echo ""
echo "=== Verify ==="
cat <<'EOF'
istioctl authn tls-check product-service.ecommerce.svc.cluster.local
istioctl proxy-status
kubectl get peerauthentication,destinationrule,virtualservice,authorizationpolicy -n ecommerce
EOF
