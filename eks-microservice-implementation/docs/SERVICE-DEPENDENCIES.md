# Deployment & Runtime Dependencies

What must exist before what — platform layer, secrets flow, data stores, and how services talk to each other.

All paths are relative to repo root unless noted.

---

## Full platform stack (visibility map)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ AWS Account 879381241087 · region ap-south-1                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ aws-github-oidc-terraform/     → IAM role for GitHub Actions → ECR push     │
│ eks/eks-infra/                 → VPC, EKS 1.33, managed NG, EBS CSI (IRSA)  │
├─────────────────────────────────────────────────────────────────────────────┤
│ eks/k8s-services/                                                           │
│   aws-load-balancer-controller/  → ALB for all Ingresses                    │
│   argocd/                        → GitOps + shared ALB + *.livingdevops.org │
│   vault-eso/                     → Vault (dev) + ESO controller             │
│   logging-monitoring/            → Prometheus, Grafana, Loki, Promtail      │
│   kartenpter/                    → Karpenter node autoscaling               │
├─────────────────────────────────────────────────────────────────────────────┤
│ ECR (9 repos)                  → ecommerce-* container images               │
├─────────────────────────────────────────────────────────────────────────────┤
│ eks-microservice-implementation/                                            │
│   infra/cnpg-operator/         → CloudNativePG operator (cnpg-system)       │
│   infra/vault-secrets/         → Vault writes + ESO ExternalSecrets         │
│   helm-ecommerce/              → All app workloads (ecommerce ns)           │
│   apps/seed-job/               → Product seed Job                             │
│   infra/observability/         → PodMonitors, alerts, Grafana dashboards    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Deployment dependency chain (strict order)

```
AWS account + credentials
  └── (optional) aws-github-oidc-terraform
  └── eks/eks-infra
        └── aws eks update-kubeconfig
        └── ECR repos (9 × ecommerce-*)
        └── aws-load-balancer-controller
              └── argocd  ← creates shared ALB + wildcard DNS
                    └── vault-eso  ← Vault server + ESO CRDs/controller
                          └── logging-monitoring  ← Prometheus/Grafana/Loki
                          └── kartenpter  ← optional parallel; helps scheduling
        └── Build/push images (GitHub Actions or docker)
        └── infra/cnpg-operator
        └── infra/vault-secrets STAGE 1  ← passwords into Vault only
              └── kubectl create ns ecommerce
              └── infra/vault-secrets STAGE 2  ← ESO → K8s secrets
                    └── helm-ecommerce install
                          └── seed-job (Helm hook or manual)
                          └── infra/observability
                          └── (optional) argocd/application.yaml
```

**Hard rule:** Stage 2 vault-secrets and all 6 K8s secrets must exist **before** `helm install`. CNPG sets the DB password only at first bootstrap (`initdb`).

---

## Platform components — what each provides

| Component | Path | Namespace | Provides | Depends on |
|-----------|------|-----------|----------|------------|
| **EKS cluster** | `eks/eks-infra/` | — | Compute, CNI, API | VPC, IAM |
| **EBS CSI** | `eks/eks-infra/` (IRSA) | `kube-system` | gp2 PVCs | EKS |
| **ALB controller** | `eks/k8s-services/aws-load-balancer-controller/` | `kube-system` | `Ingress` → ALB | EKS, IRSA |
| **ArgoCD** | `eks/k8s-services/argocd/` | `argocd` | GitOps, shared ALB group | ALB controller |
| **Vault** | `eks/k8s-services/vault-eso/` | `vault` | KV secret store (dev token `root`) | EKS, ALB |
| **ESO controller** | `eks/k8s-services/vault-eso/` | `external-secrets` | Sync Vault → K8s Secret | Vault, CRDs |
| **Prometheus/Grafana** | `eks/k8s-services/logging-monitoring/` | `monitoring` | Metrics, dashboards, Loki logs | EKS, ALB |
| **Karpenter** | `eks/k8s-services/kartenpter/` | `karpenter` | Auto EC2 nodes when Pending | EKS, subnets/SG tags |
| **CNPG operator** | `infra/cnpg-operator/` | `cnpg-system` | Postgres `Cluster` CRD | EKS |
| **vault-secrets TF** | `infra/vault-secrets/` | `ecommerce` (+ cluster-wide store) | 6 synced secrets | Vault, ESO, ecommerce ns |
| **ECR images** | `.github/workflows/` or manual docker | — | `:latest` images for Deployments | ECR repos, OIDC or AWS creds |
| **helm-ecommerce** | `helm-ecommerce/` | `ecommerce` | All microservices + data | Everything above |
| **observability TF** | `infra/observability/` | `monitoring` | App scrape + alerts + dashboards | monitoring stack + running pods |

---

## Namespaces at a glance

| Namespace | Main workloads |
|-----------|----------------|
| `kube-system` | ALB controller, CoreDNS, kube-proxy, EBS CSI |
| `argocd` | ArgoCD server, repo-server, application-controller |
| `vault` | Vault server |
| `external-secrets` | ESO controller |
| `monitoring` | Prometheus, Grafana, Alertmanager, Loki, Promtail |
| `karpenter` | Karpenter controller |
| `cnpg-system` | CloudNativePG operator |
| `ecommerce` | All microservices, Redis, RabbitMQ, 4× CNPG clusters, ingress |

---

## Ingress & DNS (shared ALB)

All use ALB group **`k8sbatch-shared-alb`** and ACM cert on `*.livingdevops.org`.

| Host | Backend | Installed by |
|------|---------|--------------|
| `argocd.livingdevops.org` | ArgoCD server | `eks/k8s-services/argocd/` |
| `vault.livingdevops.org` | Vault UI/API | `eks/k8s-services/vault-eso/` |
| `grafana.livingdevops.org` | Grafana | `eks/k8s-services/logging-monitoring/` |
| `prometheus.livingdevops.org` | Prometheus | `eks/k8s-services/logging-monitoring/` |
| `shop.livingdevops.org` | frontend + api-gateway | `helm-ecommerce/` |

Credentials:

| UI | Login |
|----|-------|
| ArgoCD | `admin` + `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' \| base64 -d` |
| Vault | token `root` |
| Grafana | `admin` / `admin123` |

---

## Secrets flow: Vault → ESO → pods

```
infra/vault-secrets (terraform)
  random passwords → Vault KV secret/ecommerce/*
        ↓
External Secrets Operator (ClusterSecretStore vault-backend)
        ↓
Kubernetes Secrets in namespace ecommerce
        ↓
Pod env / CNPG bootstrap secretRef
```

| K8s Secret | Vault path | Used by |
|------------|------------|---------|
| `db-credentials` | `secret/ecommerce/database` | product, user, order, payment services |
| `db-app-credentials` | `secret/ecommerce/database` | CNPG `Cluster` bootstrap only |
| `redis-credentials` | `secret/ecommerce/redis` | redis Deployment, cart-service |
| `rabbitmq-credentials` | `secret/ecommerce/rabbitmq` | rabbitmq StatefulSet, order-service, notification-service |
| `app-secrets` | `secret/ecommerce/app`, `/razorpay` | user, order, payment (JWT, Razorpay) |
| `aws-credentials` | `secret/ecommerce/aws` | notification-service (SES) |

Verify anytime:

```bash
kubectl get externalsecret,secret -n ecommerce
kubectl describe externalsecret db-credentials -n ecommerce
```

---

## ECR images → Helm deployments

| ECR repository | Helm / Deployment |
|----------------|-------------------|
| `ecommerce-product-service` | product-service |
| `ecommerce-user-service` | user-service |
| `ecommerce-cart-service` | cart-service |
| `ecommerce-order-service` | order-service |
| `ecommerce-payment-service` | payment-service |
| `ecommerce-notification-service` | notification-service |
| `ecommerce-api-gateway` | api-gateway |
| `ecommerce-frontend` | frontend |
| `ecommerce-seed` | seed-data Job |

Non-ECR images (from chart `values.yaml`): `redis:7-alpine`, `rabbitmq:3.12-management-alpine`, `ghcr.io/cloudnative-pg/postgresql:15.4`.

---

## Data stores → services

| Store | K8s resource | DNS (in-cluster) | Port | Consumers |
|-------|--------------|------------------|------|-----------|
| PostgreSQL products | CNPG `Cluster` products | `products-rw.ecommerce.svc` | 5432 | product-service |
| PostgreSQL users | CNPG `Cluster` users | `users-rw.ecommerce.svc` | 5432 | user-service |
| PostgreSQL orders | CNPG `Cluster` orders | `orders-rw.ecommerce.svc` | 5432 | order-service |
| PostgreSQL payments | CNPG `Cluster` payments | `payments-rw.ecommerce.svc` | 5432 | payment-service |
| Redis | Deployment redis | `redis.ecommerce.svc` | 6379 | cart-service |
| RabbitMQ | StatefulSet rabbitmq | `rabbitmq.ecommerce.svc` | 5672 | order-service (pub), notification-service (sub) |

Storage: 1Gi gp2 PVC per CNPG cluster + 1Gi for RabbitMQ. Requires EBS CSI from `eks-infra`.

---

## Microservice startup order (runtime)

Helm applies everything at once, but **healthy** order is roughly:

```
1.  redis, rabbitmq
2.  CNPG clusters (products, users, orders, payments)
3.  product-service
4.  user-service
5.  cart-service          (needs redis + product-service)
6.  order-service         (needs DB + cart + product + rabbitmq)
7.  payment-service       (needs DB + order-service)
8.  notification-service  (needs rabbitmq + AWS creds)
9.  api-gateway           (needs all 5 backends)
10. frontend              (needs api-gateway / ingress)
11. seed-job              (needs api-gateway + product-service)
```

Watch rollout:

```bash
kubectl get pods -n ecommerce -w
kubectl get cluster -n ecommerce
```

---

## Communication overview

```
                         shop.livingdevops.org
                                 │
                    ┌────────────┴────────────┐
                    │        Frontend         │
                    └────────────┬────────────┘
                                 │ HTTP
                    ┌────────────▼────────────┐
                    │      API Gateway        │ :80
                    └──┬───┬───┬───┬───┬──────┘
           ┌───────────┘   │   │   │   └───────────┐
           ▼               ▼   ▼   ▼               ▼
    product-service  user-service  cart-service  order-service  payment-service
           │               │         │              │               │
           ▼               ▼         ▼              ▼               ▼
      products-rw      users-rw    redis      orders-rw       payments-rw
                                    │              │
                                    ▼              ▼
                              product-service   rabbitmq ──► notification-service ──► AWS SES
```

### Sync HTTP

| From | To | Purpose |
|------|-----|---------|
| Browser | Frontend / API Gateway | Shop UI + `/api/*` |
| API Gateway | product / user / cart / order / payment | Path-based routing |
| Cart Service | Product Service :8001 | Validate product, price, stock |
| Order Service | Cart Service :8003 | Fetch cart at checkout |
| Order Service | Product Service :8001 | Stock check / update |
| Payment Service | Order Service :8004 | Update order after payment |
| Seed Job | API Gateway | POST 15 products |

### Async (RabbitMQ)

| Publisher | Events | Consumer |
|-----------|--------|----------|
| order-service | `order.created`, `order.confirmed`, `order.cancelled` | notification-service |

### External APIs

| Service | External | Purpose |
|---------|----------|---------|
| payment-service | Razorpay | Payments |
| notification-service | AWS SES | Order/payment emails |

---

## Observability dependencies

| Layer | What | Needs |
|-------|------|-------|
| **Cluster** | Prometheus, Grafana, Loki, Promtail | `logging-monitoring/` |
| **App** | PodMonitors, PrometheusRules, 2 Grafana dashboards | `infra/observability/` + running `ecommerce` pods |

App metrics ports (scraped by PodMonitor):

| Service | Metrics port |
|---------|--------------|
| product-service | 8001 |
| user-service | 8002 |
| cart-service | 8003 |
| order-service | 8004 |
| payment-service | 8005 |
| notification-service | 8006 |
| api-gateway | 80 |

Logs: Promtail (DaemonSet) → Loki → Grafana Explore. No per-app log config needed.

---

## Karpenter vs managed node group

| | Managed node group | Karpenter |
|--|-------------------|-----------|
| **Defined in** | `eks/eks-infra/` | `eks/k8s-services/kartenpter/` |
| **When used** | Baseline cluster capacity | Burst when pods Pending |
| **Blocks app deploy?** | Yes (need at least 1 node) | No |
| **Instance types** | Fixed in TF | NodePool (e.g. t3 family, on-demand) |

If pods stay Pending with `Insufficient cpu` or max pods per node, Karpenter should provision nodes — or scale the managed node group.

---

## CI/CD dependency

```
GitHub repo (main branch)
  └── workflow_dispatch: build-deploy-ms.yaml
        └── OIDC → arn:aws:iam::879381241087:role/aws-github-oidc-march26
              └── docker build --platform linux/amd64
              └── push to 879381241087.dkr.ecr.ap-south-1.amazonaws.com/ecommerce-*:latest
```

Helm `values.yaml` references `:latest` tags. After image push, restart deployments or run `helm upgrade` to pull new images (`imagePullPolicy: Always`).

Optional GitOps: `argocd/application.yaml` syncs `helm-ecommerce/` from Git.

---

## See also

- [DEPLOYMENT-SEQUENCE.md](./DEPLOYMENT-SEQUENCE.md) — full command-by-command deploy steps
- [SERVICE-MAP.md](./SERVICE-MAP.md) — one section per service and platform component
