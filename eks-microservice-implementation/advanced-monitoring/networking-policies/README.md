# Network Policies — Ecommerce Namespace

Default-deny ingress with explicit allow rules matching the [service dependency graph](../../docs/SERVICE-DEPENDENCIES.md).

## Traffic model

```
Internet → ALB (VPC) → frontend / api-gateway
api-gateway → microservices (8001–8006)
cart-service → product-service, redis
order-service → cart-service, product-service, rabbitmq, postgres
payment-service → order-service, postgres
notification-service → rabbitmq
microservices → CNPG (products-rw, users-rw, orders-rw, payments-rw)
monitoring → scrape /metrics on all services
payment / notification → HTTPS egress (Razorpay, AWS SES)
```

## Files (apply in order)

| File | Purpose |
|------|---------|
| `00-namespace-label.yaml` | Mark namespace for policy enforcement |
| `01-default-deny-ingress.yaml` | Deny all ingress unless allowed |
| `02-allow-dns-egress.yaml` | Allow CoreDNS lookup (all pods) |
| `03-frontend.yaml` | ALB → frontend:80 |
| `04-api-gateway.yaml` | frontend + ALB → api-gateway; gateway → backends |
| `05-product-service.yaml` | gateway, cart, order → product:8001 |
| `06-user-service.yaml` | gateway → user:8002 |
| `07-cart-service.yaml` | gateway, order → cart:8003 |
| `08-order-service.yaml` | gateway, payment → order:8004 |
| `09-payment-service.yaml` | gateway → payment:8005 + external HTTPS |
| `10-notification-service.yaml` | rabbitmq → notification + external HTTPS |
| `11-redis.yaml` | cart-service → redis:6379 |
| `12-rabbitmq.yaml` | order pub, notification sub |
| `13-cnpg-postgres.yaml` | Per-cluster Postgres ingress |
| `14-allow-prometheus-scrape.yaml` | monitoring → /metrics |
| `15-allow-kubelet-probes.yaml` | Node/kubelet → health probes (VPC CIDR) |
| `16-seed-job.yaml` | seed job → api-gateway egress |

## Apply (do when ready)

```bash
cd eks-microservice-implementation/advanced-monitoring/networking-policies

# Preview
kubectl apply -f . --dry-run=client

# Apply all (ordered by filename)
kubectl apply -f .

# Verify
kubectl get networkpolicy -n ecommerce
kubectl describe networkpolicy -n ecommerce
```

## Verify traffic after apply

```bash
# From api-gateway pod — should reach backends
kubectl exec -n ecommerce deploy/api-gateway -- curl -sf http://product-service:8001/health

# From cart pod — should reach redis + product
kubectl exec -n ecommerce deploy/cart-service -- curl -sf http://product-service:8001/health

# Prometheus targets (after 14-allow-prometheus-scrape)
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090
# http://localhost:9090/targets
```

## Rollback

```bash
kubectl delete -f . --ignore-not-found
kubectl label namespace ecommerce network-policy/enabled-
```

## Notes

- ALB traffic arrives from the VPC (`10.0.0.0/16`). Frontend and api-gateway policies allow that CIDR on port 80.
- If shop ingress breaks, confirm ALB target health and that `10.0.0.0/16` matches your VPC (`eks/eks-infra/network.tf`).
- NetworkPolicy does **not** encrypt traffic — pair with `service-mesh/` for mTLS.
