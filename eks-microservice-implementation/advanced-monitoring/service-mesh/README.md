# Service Mesh (Istio) — Ecommerce Namespace

Istio adds **mTLS**, **L7 traffic management** (retries, timeouts, circuit breaking), **authorization policies**, and **mesh-native metrics** on top of NetworkPolicy.

Works alongside the existing **ALB ingress** — external traffic still enters via `shop.livingdevops.org`; Istio sidecars handle east-west traffic inside the mesh.

## What you get

| Feature | Istio resource |
|---------|----------------|
| mTLS between services | `PeerAuthentication` + `DestinationRule` |
| Retries / timeouts | `VirtualService` |
| Circuit breaking | `DestinationRule` (outlier detection) |
| L7 authorization | `AuthorizationPolicy` |
| External APIs (Razorpay, SES) | `ServiceEntry` |
| Extra Prometheus metrics | `Telemetry` |

## Prerequisites

- `networking-policies/` applied and verified (recommended)
- Helm 3.x
- kubectl context pointing at `eks-cluster`

---

## Step 1 — Install Istio control plane (commands only)

```bash
# Add Istio Helm repo
helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo update

# Create istio-system namespace
kubectl create namespace istio-system --dry-run=client -o yaml | kubectl apply -f -

# Install base CRDs
helm install istio-base istio/base \
  -n istio-system \
  --set defaultRevision=default \
  --wait

# Install istiod (control plane)
helm install istiod istio/istiod \
  -n istio-system \
  --wait \
  --set meshConfig.enablePrometheusMerge=true \
  --set meshConfig.defaultConfig.holdApplicationUntilProxyStarts=true

# Verify
kubectl get pods -n istio-system
kubectl get crd | grep istio
```

Optional — Istio ingress gateway (not required; you use AWS ALB):

```bash
# Skip if keeping ALB-only ingress
# helm install istio-ingressgateway istio/gateway -n istio-system --wait
```

---

## Step 2 — Enable sidecar injection

```bash
# Label namespace (also in 00-namespace-labels.yaml)
kubectl label namespace ecommerce istio-injection=enabled --overwrite

# Apply mesh policies BEFORE restart (so sidecars pick up config)
kubectl apply -f advanced-monitoring/service-mesh/

# Restart workloads to inject sidecars
kubectl rollout restart deployment -n ecommerce
kubectl rollout restart statefulset -n ecommerce

# Wait for sidecars (2/2 or 3/3 READY)
kubectl get pods -n ecommerce
kubectl get pods -n ecommerce -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}{end}'
```

Each app pod should show `istio-proxy` container alongside the app container.

---

## Step 3 — Verify mesh

```bash
# mTLS status (after PERMISSIVE → STRICT migration)
istioctl authn tls-check product-service.ecommerce.svc.cluster.local

# Proxy config
istioctl proxy-status

# Mesh metrics in Prometheus (after Telemetry applied)
# Query: istio_requests_total{destination_service_namespace="ecommerce"}
```

Install `istioctl` locally:

```bash
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.24.2 sh -
export PATH=$PATH:$PWD/istio-1.24.2/bin
```

---

## Manifest files

| File | Purpose |
|------|---------|
| `00-namespace-labels.yaml` | `istio-injection=enabled` on ecommerce |
| `01-peer-authentication.yaml` | mTLS mode (PERMISSIVE → STRICT) |
| `02-destination-rules.yaml` | mTLS, connection pools, circuit breakers |
| `03-virtual-services.yaml` | Timeouts and retries per route |
| `04-authorization-policies.yaml` | L7 allow/deny matching service graph |
| `05-serviceentries-external.yaml` | Razorpay + AWS SES external hosts |
| `06-telemetry.yaml` | Prometheus metrics from sidecars |
| `07-envoy-filter-access-logs.yaml` | JSON access logs to stdout for Loki |

## Apply mesh manifests (do when ready)

```bash
cd eks-microservice-implementation/advanced-monitoring/service-mesh

kubectl apply -f . --dry-run=client
kubectl apply -f .
```

## Rollback

```bash
# Remove mesh policies
kubectl delete -f advanced-monitoring/service-mesh/ --ignore-not-found

# Disable injection + restart to remove sidecars
kubectl label namespace ecommerce istio-injection-

kubectl rollout restart deployment -n ecommerce
kubectl rollout restart statefulset -n ecommerce

# Uninstall Istio (last)
helm uninstall istiod -n istio-system
helm uninstall istio-base -n istio-system
kubectl delete namespace istio-system
```

## Upgrade mTLS to STRICT (after all sidecars injected)

Edit `01-peer-authentication.yaml`: change `PERMISSIVE` → `STRICT`, then:

```bash
kubectl apply -f 01-peer-authentication.yaml
```

## Integrate with existing monitoring

Mesh metrics appear in Prometheus automatically when `enablePrometheusMerge=true`. Grafana dashboards can add panels for:

```promql
sum(rate(istio_requests_total{destination_service_namespace="ecommerce"}[5m])) by (destination_service_name, response_code)
histogram_quantile(0.95, sum(rate(istio_request_duration_milliseconds_bucket{destination_service_namespace="ecommerce"}[5m])) by (le, destination_service_name))
```

See [`docs/MONITORING.md`](../../docs/MONITORING.md) for the base stack.
