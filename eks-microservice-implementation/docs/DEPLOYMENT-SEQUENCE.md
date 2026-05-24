# E-commerce EKS — Full Deployment Sequence

Run every step **top to bottom**. Each block is one thing to do. Commands are copy-paste ready.

**Region:** `ap-south-1`  
**Cluster:** `eks-cluster`  
**Account / ECR:** `879381241087.dkr.ecr.ap-south-1.amazonaws.com`  
**Domain:** `*.livingdevops.org` (shared ALB group `k8sbatch-shared-alb`)

---

## 0 — Prerequisites (one time on your laptop)

Install and configure tools before touching AWS.

```bash
# AWS CLI — credentials for account 879381241087
aws configure
aws sts get-caller-identity

# Terraform (match repo versions.tf; 1.12.x works)
terraform version

# kubectl + helm
kubectl version --client
helm version

# Docker (for manual image builds)
docker version
```

Clone the repo:

```bash
git clone https://github.com/akhileshmishrabiz/k8sbootcamp-march26.git
cd k8sbootcamp-march26
```

Before every `terraform apply`, check each module's `backend` block and `provider.tf` (S3 bucket, region, cluster name). Update if you use your own state bucket.

---

## 1 — GitHub OIDC for CI (optional but recommended)

Lets GitHub Actions push to ECR without long-lived AWS keys.

```bash
cd aws-github-oidc-terraform
terraform init
terraform apply
```

Verify:

```bash
terraform output aws_iam_role_arn
# Expected: arn:aws:iam::879381241087:role/aws-github-oidc-march26
```

---

## 2 — EKS cluster (VPC + nodes + EBS CSI)

Creates the cluster, managed node group, and EBS CSI driver (needed for CNPG and RabbitMQ PVCs).

```bash
cd ../eks/eks-infra
terraform init
terraform apply
```

Verify:

```bash
aws eks list-clusters --region ap-south-1
aws eks describe-cluster --name eks-cluster --region ap-south-1 \
  --query 'cluster.status'
```

---

## 3 — Configure kubectl

```bash
aws eks update-kubeconfig --name eks-cluster --region ap-south-1

# Optional: shorter context name
kubectl config get-contexts
kubectl config rename-context \
  arn:aws:eks:ap-south-1:879381241087:cluster/eks-cluster \
  eks-cluster

kubectl get nodes
kubectl get ns
```

You should see at least one managed node in `Ready` state.

---

## 4 — Create ECR repositories (one time per account)

Nine repos — one per app image. Skip if they already exist.

```bash
REGION=ap-south-1
for repo in \
  ecommerce-product-service \
  ecommerce-user-service \
  ecommerce-cart-service \
  ecommerce-order-service \
  ecommerce-payment-service \
  ecommerce-notification-service \
  ecommerce-api-gateway \
  ecommerce-frontend \
  ecommerce-seed
do
  aws ecr create-repository \
    --repository-name "$repo" \
    --region "$REGION" \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability MUTABLE \
  || true
done
```

Verify:

```bash
aws ecr describe-repositories --region ap-south-1 \
  --query 'repositories[].repositoryName' --output table
```

---

## 5 — AWS Load Balancer Controller

Required before any Ingress with `ingressClassName: alb` gets a real ALB.

```bash
cd ../k8s-services/aws-load-balancer-controller
terraform init
terraform apply
```

Verify:

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
kubectl get deployment -n kube-system aws-load-balancer-controller
```

---

## 6 — ArgoCD

Installs ArgoCD and the **first** ingress on the shared ALB. Creates wildcard DNS for `*.livingdevops.org`.

```bash
cd ../argocd
terraform init
terraform apply
```

Verify:

```bash
kubectl get pods -n argocd
kubectl get ingress -n argocd

# Initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
# Login: admin / <password above> at https://argocd.livingdevops.org
```

---

## 7 — Vault + External Secrets Operator (ESO)

Vault runs in dev mode (root token `root`). ESO controller syncs Vault → Kubernetes secrets later.

```bash
cd ../vault-eso
terraform init
terraform apply
```

Verify:

```bash
kubectl get pods -n vault
kubectl get pods -n external-secrets
kubectl get ingress -n vault

# Vault UI: https://vault.livingdevops.org — token: root
# Local access (needed for vault-secrets terraform):
kubectl port-forward -n vault svc/vault 8200:8200 &
curl -s http://localhost:8200/v1/sys/health | head
```

Keep the port-forward running for steps 14–15, or start it again before those steps.

---

## 8 — Logging & Monitoring (Prometheus, Grafana, Loki)

Cluster-wide observability stack. App dashboards are added later in step 19.

```bash
cd ../logging-monitoring
terraform init
terraform apply
```

Verify:

```bash
kubectl get pods -n monitoring
kubectl get ingress -n monitoring

# Grafana:  https://grafana.livingdevops.org  (admin / admin123)
# Prometheus: https://prometheus.livingdevops.org
```

---

## 9 — Karpenter (node autoscaling)

Adds burst EC2 capacity when pods cannot schedule on the managed node group. Does not block app deploy, but run it before heavy workloads.

```bash
cd ../kartenpter
terraform init
terraform apply
```

Verify:

```bash
kubectl get pods -n karpenter
kubectl get nodepools
kubectl get ec2nodeclasses

# When pods are Pending, Karpenter should create nodes:
kubectl get nodes -l karpenter.sh/nodepool
kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter --tail=50
```

---

## 10 — Verify all cluster services are up

Quick health check before building app images.

```bash
kubectl get pods -A | grep -v Running | grep -v Completed
# Expect only header line, or known Pending (e.g. karpenter anti-affinity on small clusters)

kubectl get ingress -A
# Expect: argocd, vault, grafana, prometheus hostnames
```

---

## 11 — Build and push container images

Images must be **linux/amd64** for EKS nodes. Helm chart expects `:latest` tags in ECR.

### Option A — GitHub Actions (recommended)

1. Push repo to GitHub (fork if needed).
2. GitHub → Actions → **E-commerce Build & Deploy** → **Run workflow**.
3. Workflow builds and pushes all 9 images using OIDC role from step 1.

Workflow file: `.github/workflows/build-deploy-ms.yaml`

Images pushed:

| Service | ECR repo |
|---------|----------|
| product-service | `ecommerce-product-service` |
| user-service | `ecommerce-user-service` |
| cart-service | `ecommerce-cart-service` |
| order-service | `ecommerce-order-service` |
| payment-service | `ecommerce-payment-service` |
| notification-service | `ecommerce-notification-service` |
| api-gateway | `ecommerce-api-gateway` |
| frontend | `ecommerce-frontend` |
| seed-job | `ecommerce-seed` |

Verify after workflow completes:

```bash
aws ecr describe-images --repository-name ecommerce-product-service --region ap-south-1 \
  --query 'imageDetails[0].imageTags'
```

### Option B — Manual docker build (all 9 images)

```bash
cd eks-microservice-implementation
ECR=879381241087.dkr.ecr.ap-south-1.amazonaws.com
REGION=ap-south-1

aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin $ECR

build_push() {
  local dir=$1 repo=$2
  docker build --platform linux/amd64 -t $ECR/$repo:latest "$dir"
  docker push $ECR/$repo:latest
}

build_push apps/services/product-service       ecommerce-product-service
build_push apps/services/user-service          ecommerce-user-service
build_push apps/services/cart-service          ecommerce-cart-service
build_push apps/services/order-service         ecommerce-order-service
build_push apps/services/payment-service       ecommerce-payment-service
build_push apps/services/notification-service  ecommerce-notification-service
build_push apps/api-gateway                    ecommerce-api-gateway
build_push apps/frontend                         ecommerce-frontend
build_push apps/seed-job                         ecommerce-seed
```

Verify all tags exist:

```bash
for repo in ecommerce-product-service ecommerce-user-service ecommerce-cart-service \
  ecommerce-order-service ecommerce-payment-service ecommerce-notification-service \
  ecommerce-api-gateway ecommerce-frontend ecommerce-seed; do
  echo -n "$repo: "
  aws ecr describe-images --repository-name $repo --region ap-south-1 \
    --query 'imageDetails[?contains(imageTags, `latest`)].imageTags' --output text
done
```

---

## 12 — CloudNativePG operator

Installs the Postgres operator and `Cluster` CRD used by the Helm chart.

```bash
cd infra/cnpg-operator
terraform init
terraform apply
```

Verify:

```bash
kubectl get pods -n cnpg-system
kubectl get crd clusters.postgresql.cnpg.io
```

---

## 13 — Vault secrets — Stage 1 (write passwords to Vault only)

Generates random DB, Redis, RabbitMQ, JWT passwords and writes them to Vault KV paths under `secret/ecommerce/*`.  
**Do not** enable ESO yet (`enable_eso_secrets=false` is the default).

```bash
# Start Vault port-forward if not already running
kubectl port-forward -n vault svc/vault 8200:8200 &

cd ../vault-secrets
terraform init
terraform apply \
  -var vault_addr=http://localhost:8200 \
  -var vault_token=root
```

Verify Vault paths (optional):

```bash
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=root
vault kv list secret/ecommerce
# Expect: database, redis, rabbitmq, app, razorpay, aws
```

---

## 14 — Create `ecommerce` namespace

ESO `ExternalSecret` objects need this namespace to exist before Stage 2.

```bash
kubectl create namespace ecommerce
```

Verify:

```bash
kubectl get namespace ecommerce
```

---

## 15 — Vault secrets — Stage 2 (ESO → Kubernetes secrets)

Creates `ClusterSecretStore` + 6 `ExternalSecret`s that sync Vault into K8s secrets.

**Critical:** Run this **before** `helm install`. CNPG reads `db-app-credentials` at Postgres bootstrap time.

```bash
cd ../vault-secrets   # eks-microservice-implementation/infra/vault-secrets
terraform apply \
  -var vault_addr=http://localhost:8200 \
  -var vault_token=root \
  -var enable_eso_secrets=true
```

Verify all secrets synced:

```bash
kubectl get clustersecretstore
kubectl get externalsecret -n ecommerce
kubectl get secret -n ecommerce
# Expect: db-credentials, db-app-credentials, redis-credentials,
#         rabbitmq-credentials, app-secrets, aws-credentials
```

If any ExternalSecret shows error, check ESO logs:

```bash
kubectl logs -n external-secrets -l app.kubernetes.io/name=external-secrets --tail=50
```

---

## 16 — Deploy the app (Helm chart)

Deploys all microservices, 4 CNPG Postgres clusters, Redis, RabbitMQ, ingress, and seed-job hook.

```bash
cd ../../helm-ecommerce
helm install ecommerce . -n ecommerce --create-namespace
```

Or upgrade if already installed:

```bash
helm upgrade ecommerce . -n ecommerce
```

Wait for rollout:

```bash
kubectl get pods -n ecommerce -w
# Ctrl+C when all Running (seed-job may show Completed)
```

Verify:

```bash
kubectl get pods -n ecommerce
kubectl get cluster -n ecommerce          # CNPG — all should be Cluster in sync / Ready
kubectl get svc -n ecommerce
kubectl get ingress -n ecommerce
kubectl get pvc -n ecommerce
```

Shop URL: **https://shop.livingdevops.org**

---

## 17 — Seed product data

The Helm chart runs a **post-install Job** automatically (`seedJob.enabled: true` in `values.yaml`).  
If it failed or you disabled it, run manually:

```bash
# Check if seed job already completed
kubectl get jobs -n ecommerce
kubectl logs -n ecommerce job/seed-data-job

# Manual re-run (delete old job first)
kubectl delete job seed-data-job -n ecommerce --ignore-not-found
kubectl apply -f - <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: seed-data-job
  namespace: ecommerce
spec:
  ttlSecondsAfterFinished: 300
  backoffLimit: 3
  template:
    spec:
      containers:
      - name: seed-data
        image: 879381241087.dkr.ecr.ap-south-1.amazonaws.com/ecommerce-seed:latest
        env:
        - name: API_URL
          value: "http://api-gateway.ecommerce.svc.cluster.local"
      restartPolicy: Never
EOF
```

Verify products exist:

```bash
kubectl logs -n ecommerce job/seed-data-job
curl -s https://shop.livingdevops.org/api/products | head
```

Test user (from seed-job docs):

```
Email: john.doe@example.com
Password: NewPassword123!
```

---

## 18 — App observability (PodMonitors, alerts, dashboards)

Wires Prometheus/Grafana to scrape the ecommerce microservices. Requires step 8 (monitoring stack) and step 16 (running pods).

```bash
cd ../infra/observability
terraform init
terraform apply
```

Verify:

```bash
kubectl get podmonitors -n monitoring -l app.kubernetes.io/part-of=ecommerce
kubectl get prometheusrules -n monitoring ecommerce-app-rules
kubectl get cm -n monitoring -l grafana_dashboard=1

# Open Grafana → dashboards "Ecommerce — Service RED" and "Ecommerce — Logs (Loki)"
# Open Grafana → folder "sre-teaching" for 8 SRE curriculum dashboards
# https://grafana.livingdevops.org
```

---

## 19 — ArgoCD GitOps (optional)

Syncs the Helm chart from Git instead of manual `helm install`.

```bash
kubectl apply -f ../../argocd/application.yaml
```

Verify in UI or CLI:

```bash
kubectl get application -n argocd ecommerce
# https://argocd.livingdevops.org — app "ecommerce" should be Synced / Healthy
```

---

## 20 — Final verification checklist

Run through this list when everything should be working.

```bash
# Nodes
kubectl get nodes

# Cluster platform
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
kubectl get pods -n argocd
kubectl get pods -n vault
kubectl get pods -n external-secrets
kubectl get pods -n monitoring
kubectl get pods -n karpenter
kubectl get pods -n cnpg-system

# App
kubectl get pods,svc,ingress,pvc,cluster -n ecommerce
kubectl get externalsecret,secret -n ecommerce
kubectl get jobs -n ecommerce

# Endpoints (browser)
# Shop:       https://shop.livingdevops.org
# ArgoCD:     https://argocd.livingdevops.org
# Vault:      https://vault.livingdevops.org  (token: root)
# Grafana:    https://grafana.livingdevops.org  (admin / admin123)
# Prometheus: https://prometheus.livingdevops.org
```

Smoke test:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://shop.livingdevops.org
curl -s https://shop.livingdevops.org/api/products | jq length
```

---

## Troubleshooting (common issues)

### ESO secrets missing / pods CrashLoop on secret mount

Stage 2 was skipped or namespace did not exist. Re-run step 15 with `enable_eso_secrets=true`.

### Postgres auth errors (`password authentication failed`)

CNPG bootstrapped **before** ESO secrets existed. Fix passwords on live clusters:

```bash
# Get password from K8s secret
kubectl get secret db-app-credentials -n ecommerce -o jsonpath='{.data.password}' | base64 -d && echo

# For each CNPG cluster pod (products, users, orders, payments):
kubectl exec -n ecommerce products-1 -- psql -U postgres -c \
  "ALTER USER ecommerce_user WITH PASSWORD '<password-from-secret>';"
# Repeat for users-1, orders-1, payments-1
kubectl rollout restart deployment -n ecommerce product-service user-service order-service payment-service
```

**Prevention:** Always complete steps 13 → 14 → 15 before step 16.

### Pods stuck Pending — insufficient CPU/memory or pod limit

Check events and node capacity:

```bash
kubectl describe pod -n ecommerce <pod-name> | tail -20
kubectl get nodes
kubectl describe nodes | grep -A5 "Allocated resources"
```

Karpenter should add nodes (step 9). If not, check Karpenter logs.

### Karpenter nodes not joining

```bash
kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter --tail=100
kubectl get nodepools,ec2nodeclasses
```

Ensure subnets and security groups are tagged with `karpenter.sh/discovery=eks-cluster`.

### Stuck EBS volumes after node drain

```bash
kubectl get volumeattachments
kubectl delete volumeattachment <name>   # if volume stuck on terminated node
```

### Image pull errors

Confirm images exist in ECR (step 11) and nodes can reach ECR (managed node IAM / VPC endpoints).

---

## Tear down (reverse order)

```bash
# Stop Vault port-forward if running
kill %1 2>/dev/null || true

# GitOps
kubectl delete application ecommerce -n argocd --ignore-not-found

# App
helm uninstall ecommerce -n ecommerce
terraform -chdir=eks-microservice-implementation/infra/observability destroy
terraform -chdir=eks-microservice-implementation/infra/vault-secrets destroy
terraform -chdir=eks-microservice-implementation/infra/cnpg-operator destroy

# Cluster services
terraform -chdir=eks/k8s-services/kartenpter destroy
terraform -chdir=eks/k8s-services/logging-monitoring destroy
terraform -chdir=eks/k8s-services/vault-eso destroy
terraform -chdir=eks/k8s-services/argocd destroy
terraform -chdir=eks/k8s-services/aws-load-balancer-controller destroy

# Cluster (last — destroys VPC)
terraform -chdir=eks/eks-infra destroy
```

ECR repos and OIDC role are not destroyed by the above — delete manually if needed.

---

## Related docs

- [SERVICE-DEPENDENCIES.md](./SERVICE-DEPENDENCIES.md) — what each layer needs from the others
- [SERVICE-MAP.md](./SERVICE-MAP.md) — per-service and platform component map
- [../infra/README.md](../infra/README.md) — Vault secret rotation
- [../helm-ecommerce/README.md](../helm-ecommerce/README.md) — chart values and secret keys
