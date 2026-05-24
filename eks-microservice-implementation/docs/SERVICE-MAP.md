# Service Map — Full Platform & Application Visibility

One section per component: image, namespace, ports, secrets, dependencies, and how to inspect it.

Default app namespace: **`ecommerce`**.

---

## Platform components

### EKS cluster + managed node group

| | |
|---|---|
| **Path** | `eks/eks-infra/` |
| **Name** | `eks-cluster` |
| **Region** | `ap-south-1` |
| **Provides** | Kubernetes API, baseline worker nodes, EBS CSI (gp2 PVCs) |
| **Inspect** | `kubectl get nodes` · `kubectl get sc` |

---

### AWS Load Balancer Controller

| | |
|---|---|
| **Path** | `eks/k8s-services/aws-load-balancer-controller/` |
| **Namespace** | `kube-system` |
| **Provides** | Watches `Ingress` with class `alb`, creates ALBs |
| **Required by** | argocd, vault, grafana, shop ingress |
| **Inspect** | `kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller` |

---

### ArgoCD

| | |
|---|---|
| **Path** | `eks/k8s-services/argocd/` |
| **Namespace** | `argocd` |
| **URL** | https://argocd.livingdevops.org |
| **Login** | user `admin`, password from `argocd-initial-admin-secret` |
| **Provides** | GitOps; optional sync of `helm-ecommerce/` via `argocd/application.yaml` |
| **Inspect** | `kubectl get pods,ingress -n argocd` · `kubectl get applications -n argocd` |

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

---

### Vault

| | |
|---|---|
| **Path** | `eks/k8s-services/vault-eso/` (Vault server) |
| **Namespace** | `vault` |
| **URL** | https://vault.livingdevops.org |
| **Token** | `root` (dev mode — not for production) |
| **Provides** | Central KV store for app passwords |
| **Inspect** | `kubectl get pods,ingress -n vault` |

Local API (for terraform vault provider):

```bash
kubectl port-forward -n vault svc/vault 8200:8200 &
export VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=root
vault kv list secret/ecommerce
```

---

### External Secrets Operator (ESO)

| | |
|---|---|
| **Path** | `eks/k8s-services/vault-eso/` (ESO install) + `infra/vault-secrets/` (ExternalSecret CRs) |
| **Namespace** | `external-secrets` (controller), secrets synced to `ecommerce` |
| **Provides** | `ClusterSecretStore vault-backend` → 6 K8s secrets |
| **Inspect** | `kubectl get pods -n external-secrets` · `kubectl get clustersecretstore` · `kubectl get externalsecret -n ecommerce` |

---

### Prometheus / Grafana / Loki

| | |
|---|---|
| **Path** | `eks/k8s-services/logging-monitoring/` |
| **Namespace** | `monitoring` |
| **Grafana** | https://grafana.livingdevops.org — `admin` / `admin123` |
| **Prometheus** | https://prometheus.livingdevops.org |
| **Provides** | Cluster metrics, log aggregation (Loki + Promtail DaemonSet), Alertmanager |
| **Inspect** | `kubectl get pods,ingress -n monitoring` |

App-level wiring (PodMonitors, dashboards): `infra/observability/`.

---

### Karpenter

| | |
|---|---|
| **Path** | `eks/k8s-services/kartenpter/` |
| **Namespace** | `karpenter` |
| **Provides** | Provisions EC2 nodes when pods are unschedulable |
| **NodePool** | `default` — on-demand, amd64, t3 family (see `nodepool.tf`) |
| **Inspect** | `kubectl get pods -n karpenter` · `kubectl get nodepools,ec2nodeclasses` · `kubectl get nodes -l karpenter.sh/nodepool` |

```bash
kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter --tail=50
```

---

### CloudNativePG operator

| | |
|---|---|
| **Path** | `infra/cnpg-operator/` |
| **Namespace** | `cnpg-system` |
| **Provides** | Manages `Cluster` CRs for Postgres |
| **Inspect** | `kubectl get pods -n cnpg-system` · `kubectl get crd clusters.postgresql.cnpg.io` |

---

### ECR (container registry)

| | |
|---|---|
| **Registry** | `879381241087.dkr.ecr.ap-south-1.amazonaws.com` |
| **Repos** | 9 × `ecommerce-*` (see application services below) |
| **Build** | GitHub Actions `.github/workflows/build-deploy-ms.yaml` or manual `docker build --platform linux/amd64` |
| **Inspect** | `aws ecr describe-repositories --region ap-south-1` |

---

## Application services (namespace `ecommerce`)

### Frontend

| | |
|---|---|
| **Image** | `879381241087.dkr.ecr.ap-south-1.amazonaws.com/ecommerce-frontend:latest` |
| **Deployment** | `frontend` |
| **Port** | 80 (nginx → React build) |
| **Ingress** | `shop.livingdevops.org` → frontend Service |
| **Depends on** | api-gateway (browser calls `/api/*`) |
| **Secrets** | None |
| **Database** | None |
| **Inspect** | `kubectl get deploy,svc frontend -n ecommerce` · `kubectl logs -n ecommerce deploy/frontend` |

---

### API Gateway (nginx)

| | |
|---|---|
| **Image** | `ecommerce-api-gateway:latest` |
| **Deployment** | `api-gateway` |
| **Port** | 80 |
| **Ingress** | `shop.livingdevops.org/api/*` |
| **Routes** | `/api/products` → product-service:8001 |
| | `/api/users` → user-service:8002 |
| | `/api/cart` → cart-service:8003 |
| | `/api/orders` → order-service:8004 |
| | `/api/payments` → payment-service:8005 |
| **Depends on** | All 5 backend services reachable |
| **Secrets** | None |
| **Inspect** | `kubectl logs -n ecommerce deploy/api-gateway` |

---

### Product Service (Go)

| | |
|---|---|
| **Image** | `ecommerce-product-service:latest` |
| **Deployment** | `product-service` |
| **Port** | 8001 (HTTP + `/metrics`) |
| **Database** | CNPG `products` → `products-rw:5432`, db `products`, user `ecommerce_user` |
| **Secrets** | `db-credentials` |
| **Calls** | Nothing (leaf service) |
| **Called by** | api-gateway, cart-service, order-service, seed-job |
| **Inspect** | `kubectl logs -n ecommerce deploy/product-service` · `kubectl get cluster products -n ecommerce` |

---

### User Service (Node.js)

| | |
|---|---|
| **Image** | `ecommerce-user-service:latest` |
| **Deployment** | `user-service` |
| **Port** | 8002 |
| **Database** | CNPG `users` → `users-rw:5432`, db `users` |
| **Secrets** | `db-credentials`, `app-secrets` (`JWT_SECRET`) |
| **Called by** | api-gateway (register, login, profile) |
| **Inspect** | `kubectl logs -n ecommerce deploy/user-service` |

---

### Cart Service (Node.js)

| | |
|---|---|
| **Image** | `ecommerce-cart-service:latest` |
| **Deployment** | `cart-service` |
| **Port** | 8003 |
| **Cache** | Redis `redis:6379` |
| **Secrets** | `redis-credentials`, `app-secrets` (`JWT_SECRET`) |
| **Calls** | `http://product-service:8001` |
| **Called by** | api-gateway, order-service |
| **Inspect** | `kubectl logs -n ecommerce deploy/cart-service` · `kubectl get deploy redis -n ecommerce` |

---

### Order Service (Go)

| | |
|---|---|
| **Image** | `ecommerce-order-service:latest` |
| **Deployment** | `order-service` |
| **Port** | 8004 |
| **Database** | CNPG `orders` → `orders-rw:5432`, db `orders` |
| **Message broker** | RabbitMQ `rabbitmq:5672` (publisher) |
| **Secrets** | `db-credentials`, `rabbitmq-credentials`, `app-secrets` |
| **Calls** | cart-service:8003, product-service:8001 |
| **Publishes** | `order.created`, `order.confirmed`, `order.cancelled` |
| **Called by** | api-gateway, payment-service |
| **Inspect** | `kubectl logs -n ecommerce deploy/order-service` |

---

### Payment Service (Python / Flask)

| | |
|---|---|
| **Image** | `ecommerce-payment-service:latest` |
| **Deployment** | `payment-service` |
| **Port** | 8005 |
| **Database** | CNPG `payments` → `payments-rw:5432`, db `payments` |
| **Secrets** | `db-credentials`, `app-secrets` (JWT + Razorpay keys) |
| **Calls** | order-service:8004, Razorpay API (external) |
| **Called by** | api-gateway |
| **Inspect** | `kubectl logs -n ecommerce deploy/payment-service` |

---

### Notification Service (Python / Flask)

| | |
|---|---|
| **Image** | `ecommerce-notification-service:latest` |
| **Deployment** | `notification-service` |
| **Port** | 8006 (internal only — not on api-gateway) |
| **Message broker** | RabbitMQ (consumer) |
| **Secrets** | `rabbitmq-credentials`, `aws-credentials` (SES) |
| **Calls** | AWS SES |
| **Inspect** | `kubectl logs -n ecommerce deploy/notification-service` |

---

## Data infrastructure (namespace `ecommerce`)

### Redis

| | |
|---|---|
| **Image** | `redis:7-alpine` (public, not ECR) |
| **Deployment** | `redis` |
| **Port** | 6379 |
| **Secrets** | `redis-credentials` (`REDIS_PASSWORD`) |
| **Used by** | cart-service |
| **Inspect** | `kubectl get deploy redis -n ecommerce` · `kubectl exec -n ecommerce deploy/redis -- redis-cli ping` |

---

### RabbitMQ

| | |
|---|---|
| **Image** | `rabbitmq:3.12-management-alpine` |
| **StatefulSet** | `rabbitmq` |
| **Ports** | 5672 (AMQP), 15672 (management, cluster-internal) |
| **Storage** | PVC `data-rabbitmq-0` (1Gi gp2) |
| **Secrets** | `rabbitmq-credentials` |
| **Used by** | order-service (publish), notification-service (consume) |
| **Inspect** | `kubectl get sts rabbitmq -n ecommerce` · `kubectl get pvc -n ecommerce` |

---

### CNPG PostgreSQL (×4 clusters)

| Cluster | RW service | Database | Bootstrap secret |
|---------|------------|----------|------------------|
| `products` | `products-rw` | `products` | `db-app-credentials` |
| `users` | `users-rw` | `users` | `db-app-credentials` |
| `orders` | `orders-rw` | `orders` | `db-app-credentials` |
| `payments` | `payments-rw` | `payments` | `db-app-credentials` |

| | |
|---|---|
| **Image** | `ghcr.io/cloudnative-pg/postgresql:15.4` |
| **Operator** | `cnpg-system` |
| **Storage** | 1Gi gp2 PVC per cluster |
| **App secret** | `db-credentials` (runtime env for services) |
| **Inspect** | `kubectl get cluster -n ecommerce` · `kubectl get pods -n ecommerce -l cnpg.io/cluster` |

```bash
# Example: connect to products DB
kubectl exec -n ecommerce products-1 -- psql -U postgres -c '\l'
```

---

## Jobs & GitOps

### Seed Job

| | |
|---|---|
| **Image** | `ecommerce-seed:latest` |
| **Job name** | `seed-data-job` |
| **Trigger** | Helm post-install hook (`seedJob.enabled: true`) or manual apply |
| **Target** | `http://api-gateway.ecommerce.svc.cluster.local` |
| **Depends on** | api-gateway + product-service healthy |
| **Purpose** | Inserts 15 sample products |
| **Inspect** | `kubectl get jobs -n ecommerce` · `kubectl logs -n ecommerce job/seed-data-job` |

Test credentials after seed:

```
Email: john.doe@example.com
Password: NewPassword123!
```

---

### ArgoCD Application (optional)

| | |
|---|---|
| **Manifest** | `argocd/application.yaml` |
| **Name** | `ecommerce` |
| **Source** | `helm-ecommerce/` on `main` branch |
| **Sync** | Automated prune + selfHeal |
| **Inspect** | `kubectl get application ecommerce -n argocd` |

---

## App observability (`infra/observability/`)

| Resource | Purpose |
|----------|---------|
| PodMonitors (×7) | Scrape `/metrics` on each microservice + api-gateway |
| PrometheusRule `ecommerce-app-rules` | RED recording rules + service/dependency alerts |
| ConfigMaps | Grafana dashboards `ecommerce-red`, `ecommerce-logs` |

| Dashboard | UID | Shows |
|-----------|-----|-------|
| Ecommerce — Service RED | `ecommerce-red` | Request rate, errors, latency p95, CPU/mem |
| Ecommerce — Logs (Loki) | `ecommerce-logs` | Log volume, tail, error filter |

```bash
kubectl get podmonitors -n monitoring -l app.kubernetes.io/part-of=ecommerce
kubectl get prometheusrules -n monitoring ecommerce-app-rules
kubectl get cm -n monitoring -l grafana_dashboard=1
```

---

## Quick reference — all ports

| Component | Port |
|-----------|------|
| product-service | 8001 |
| user-service | 8002 |
| cart-service | 8003 |
| order-service | 8004 |
| payment-service | 8005 |
| notification-service | 8006 |
| api-gateway | 80 |
| frontend | 80 |
| redis | 6379 |
| rabbitmq (AMQP) | 5672 |
| rabbitmq (mgmt) | 15672 |
| CNPG (each) | 5432 |
| Vault | 8200 |
| Grafana | 80 (via ingress) |

---

## Quick reference — dependency matrix

| Service | DB | Redis | RabbitMQ | Other services | Secrets |
|---------|:--:|:-----:|:--------:|----------------|---------|
| frontend | | | | api-gateway | — |
| api-gateway | | | | all 5 backends | — |
| product-service | ✓ | | | — | db-credentials |
| user-service | ✓ | | | — | db-credentials, app-secrets |
| cart-service | | ✓ | | product-service | redis-credentials, app-secrets |
| order-service | ✓ | | ✓ pub | cart, product | db, rabbitmq, app-secrets |
| payment-service | ✓ | | | order-service | db, app-secrets |
| notification-service | | | ✓ sub | — | rabbitmq, aws-credentials |
| redis | | | | — | redis-credentials |
| rabbitmq | | | | — | rabbitmq-credentials |
| seed-job | | | | api-gateway | — |

---

## Quick reference — all URLs

| What | URL |
|------|-----|
| Shop | https://shop.livingdevops.org |
| API (via shop) | https://shop.livingdevops.org/api/... |
| ArgoCD | https://argocd.livingdevops.org |
| Vault | https://vault.livingdevops.org |
| Grafana | https://grafana.livingdevops.org |
| Prometheus | https://prometheus.livingdevops.org |

---

## See also

- [DEPLOYMENT-SEQUENCE.md](./DEPLOYMENT-SEQUENCE.md) — full command-by-command deploy
- [SERVICE-DEPENDENCIES.md](./SERVICE-DEPENDENCIES.md) — platform dependency chain and secrets flow
