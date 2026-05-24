# E-commerce on EKS — End-to-end Deployment

This folder contains the **application layer**: the app source (`apps/`), the per-app infra (`infra/`: CNPG operator, Vault secret writes, ESO bindings), and the Helm chart (`helm-ecommerce/`) that deploys the microservices.

The **cluster layer** (VPC, EKS, ALB controller, ArgoCD, Vault server + ESO controller, monitoring) lives in `../eks/`.

```
repo/
├── eks/                                  # cluster layer (deploy first)
│   ├── eks-infra/                        # VPC + EKS cluster + EBS CSI IRSA
│   └── k8s-services/
│       ├── aws-load-balancer-controller/ # ALB controller (needed for ingresses)
│       ├── argocd/                       # ArgoCD + ingress on the shared ALB
│       ├── vault-eso/                    # Vault server (dev) + ESO controller
│       └── logging-monitoring/           # kube-prometheus-stack
│
└── eks-microservice-implementation/      # app layer (this folder)
    ├── apps/                             # source code + Dockerfiles for every image
    │   ├── frontend/                     # React/Vite SPA (nginx-served)
    │   ├── api-gateway/                  # nginx reverse-proxy in front of services
    │   ├── services/
    │   │   ├── product-service/          # Go
    │   │   ├── user-service/             # Node
    │   │   ├── cart-service/             # Node
    │   │   ├── order-service/            # Go
    │   │   ├── payment-service/          # Python (Flask)
    │   │   └── notification-service/     # Python (Flask + SES)
    │   ├── monitoring/                   # Grafana dashboards + Prometheus rules
    │   └── seed-job/                     # one-shot Job that seeds product data via the API gateway
    ├── infra/
    │   ├── cnpg-operator/                # CloudNativePG operator
    │   ├── vault-secrets/                # writes app creds to Vault + ESO bindings
    │   └── observability/                # PodMonitors, alerts, Grafana dashboards for the apps
    └── helm-ecommerce/                   # the e-commerce Helm chart
```

---

## Deployment order

Each step is a separate terraform state, image build, or `helm install`. Run them top-to-bottom — later steps assume earlier ones are healthy.

### Cluster layer — `../eks/`

| # | Path | What it creates | Why this order |
|---|------|-----------------|----------------|
| 1 | `eks/eks-infra/` | VPC, EKS 1.33 cluster, managed node group, EBS CSI driver | Everything else needs the cluster |
| 2 | — (one-time) | `aws eks update-kubeconfig --name eks-cluster` | kubectl/helm/terraform providers need a working kubeconfig |
| 3 | `eks/k8s-services/aws-load-balancer-controller/` | IRSA role + ALB controller helm release | Required before any `ingressClassName: alb` resource will get an ALB |
| 4 | `eks/k8s-services/argocd/` | ArgoCD helm release + ingress (creates the shared ALB `k8sbatch-shared-alb` and the `*.livingdevops.org` wildcard A record) | First ingress in the shared ALB group owns the wildcard DNS record |
| 5 | `eks/k8s-services/vault-eso/` | Vault server (dev mode, root token `root`) + ESO controller + vault ingress reusing the ACM cert | App layer writes to this Vault; ESO controller materialises secrets from it |
| 6 | `eks/k8s-services/logging-monitoring/` | kube-prometheus-stack (Prometheus, Grafana, Alertmanager) | Optional but expected by service dashboards |

### App layer — `eks-microservice-implementation/` (this folder)

| # | Path | What it creates | Notes |
|---|------|-----------------|-------|
| 7 | `apps/` | Build + push the 8 images to ECR (`ecommerce-{frontend,api-gateway,product-service,user-service,cart-service,order-service,payment-service,notification-service}`) | Image short names referenced from `helm-ecommerce/values.yaml` (account `879381241087`, region `ap-south-1`). Skip if images already in ECR. |
| 8 | `infra/cnpg-operator/` | CloudNativePG operator in `cnpg-system` | Installs the `Cluster` CRD the chart's PostgreSQL clusters depend on |
| 9 | `infra/vault-secrets/` (stage 1) | Random app passwords written to Vault KV `secret/ecommerce/*` | Run with `enable_eso_secrets=false` first to populate Vault |
| 10 | `infra/vault-secrets/` (stage 2) | `ClusterSecretStore` + 6 `ExternalSecret` resources | Run with `enable_eso_secrets=true`; needs the `ecommerce` namespace to exist |
| 11 | `helm-ecommerce/` | `helm install ecommerce . -n ecommerce --create-namespace` | CNPG clusters bootstrap from `db-app-credentials`; pods mount the other ESO-materialised secrets |
| 12 | `apps/seed-job/` | `kubectl apply -f seed-job.yaml` | Seeds 15 products through the api-gateway. Run once after the chart is healthy. |
| 13 | `infra/observability/` | PodMonitors, PrometheusRule, Grafana dashboard ConfigMaps | Run after the chart is up so the `ecommerce` namespace and `app=*` pod labels exist for Prometheus to discover. |

> **Step 10 ordering trick**: ESO `ExternalSecret`s reference the `ecommerce` namespace. Either create it manually (`kubectl create ns ecommerce`) before step 10, or run step 10 with `enable_eso_secrets=false` first, then `helm install` (step 11) to create the namespace, then re-run step 10 with `enable_eso_secrets=true`.

---

## Quick commands

```bash
# Cluster layer
cd ../eks/eks-infra                         && terraform init && terraform apply
aws eks update-kubeconfig --name eks-cluster
cd ../k8s-services/aws-load-balancer-controller && terraform init && terraform apply
cd ../argocd                                && terraform init && terraform apply
cd ../vault-eso                             && terraform init && terraform apply
cd ../logging-monitoring                    && terraform init && terraform apply

# App layer — build and push images (per service; example for one)
aws ecr get-login-password --region ap-south-1 \
  | docker login --username AWS --password-stdin 879381241087.dkr.ecr.ap-south-1.amazonaws.com
cd ../../../eks-microservice-implementation/apps/services/product-service
docker build -t 879381241087.dkr.ecr.ap-south-1.amazonaws.com/ecommerce-product-service:latest .
docker push 879381241087.dkr.ecr.ap-south-1.amazonaws.com/ecommerce-product-service:latest
# Repeat for: user-service, cart-service, order-service, payment-service,
#             notification-service, api-gateway, frontend

# CNPG operator
cd ../../../infra/cnpg-operator && terraform init && terraform apply

# Vault writes (port-forward Vault first)
kubectl port-forward -n vault svc/vault 8200:8200 &
cd ../vault-secrets && terraform init
terraform apply -var vault_addr=http://localhost:8200 -var vault_token=root

# Create ecommerce namespace, then enable ESO bindings
kubectl create namespace ecommerce
terraform apply -var vault_addr=http://localhost:8200 -var vault_token=root -var enable_eso_secrets=true

# App chart
cd ../../helm-ecommerce
helm install ecommerce . -n ecommerce

# Seed product data
kubectl apply -f ../apps/seed-job/seed-job.yaml

# App-level observability (PodMonitors, alerts, Grafana dashboards)
cd ../infra/observability && terraform init && terraform apply
```

---

## Endpoints

All hostnames resolve via the `*.livingdevops.org` wildcard pointing at the shared ALB `k8sbatch-shared-alb`. The ALB uses ACM cert `d7c449d8-1540-4157-8959-bc48bb44b128` for TLS.

| Service | URL |
|---------|-----|
| ArgoCD | https://argocd.livingdevops.org |
| Vault UI | https://vault.livingdevops.org (root token: `root`) |
| Grafana | https://grafana.livingdevops.org |
| Prometheus | https://prometheus.livingdevops.org |
| E-commerce UI | https://shop.livingdevops.org (from `helm-ecommerce/values.yaml`) |

---

## Tearing down (reverse order)

```bash
# App
helm uninstall ecommerce -n ecommerce
terraform -chdir=infra/vault-secrets destroy
terraform -chdir=infra/cnpg-operator destroy

# Cluster services
terraform -chdir=../eks/k8s-services/logging-monitoring destroy
terraform -chdir=../eks/k8s-services/vault-eso destroy
terraform -chdir=../eks/k8s-services/argocd destroy
terraform -chdir=../eks/k8s-services/aws-load-balancer-controller destroy

# Cluster (last — destroys VPC + NAT, expensive to recreate)
terraform -chdir=../eks/eks-infra destroy
```

---

## See also

- `docs/MONITORING.md` — full monitoring guide (Prometheus, Grafana, Loki, alerts, dashboards)
- `advanced-monitoring/` — NetworkPolicy + Istio service mesh manifests
- `docs/DEPLOYMENT-SEQUENCE.md` — full deploy order (eks-infra → k8s-services → vault → cnpg → CI → helm)
- `docs/SERVICE-DEPENDENCIES.md` — platform and service dependency chain
- `docs/SERVICE-MAP.md` — per-service and platform component map
- `dashboards/README.md` — SRE teaching Grafana dashboards (RED, USE, SLO, alerts)
- `apps/seed-job/readme.md` — seed job details (image, ECR creds, env vars)
- `apps/services/*/README.md` — per-service docs (where present)
- `infra/README.md` — detailed CNPG + Vault secret rotation flow
- `infra/observability/README.md` — PodMonitors, alert rules, dashboards, log flow
- `helm-ecommerce/README.md` — chart values, secret consumption, image registry config
