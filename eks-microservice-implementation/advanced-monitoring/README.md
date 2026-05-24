# Advanced Monitoring — Network Policies & Service Mesh

Optional **defence-in-depth** layer on top of the base observability stack (`infra/observability/`).

| Folder | Purpose |
|--------|---------|
| [`networking-policies/`](networking-policies/) | Kubernetes `NetworkPolicy` — L3/L4 pod-to-pod firewall rules |
| [`service-mesh/`](service-mesh/) | Istio — mTLS, L7 routing, retries, circuit breaking, mesh metrics |

**Prerequisites**

- EKS cluster with ecommerce workloads running (`helm-ecommerce/` in namespace `ecommerce`)
- Base monitoring stack (`eks/k8s-services/logging-monitoring/` + `infra/observability/`)
- CNI must support NetworkPolicy (AWS VPC CNI does)

**Apply order**

1. Network policies first (validate traffic still flows)
2. Install Istio control plane
3. Label namespace for sidecar injection + rollout restart
4. Apply mesh policies (PeerAuthentication, DestinationRule, VirtualService, etc.)

> **Nothing in this folder is applied automatically.** Use the commands in each subfolder README when you are ready.

---

## Quick reference

```bash
# --- Networking policies ---
kubectl apply -f advanced-monitoring/networking-policies/

# --- Service mesh (install control plane first — see service-mesh/README.md) ---
# then:
kubectl apply -f advanced-monitoring/service-mesh/
kubectl rollout restart deployment,statefulset -n ecommerce
```

See also: [`docs/MONITORING.md`](../docs/MONITORING.md)
